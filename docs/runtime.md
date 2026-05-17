# Runtime

## Как это теперь работает

Проект больше не запускает свой Python-оркестратор. Kubernetes запускает один
pod `radio`, а внутри него отдельные контейнеры для узлов пайплайна:

```text
search -> PostgreSQL -> prefetch -> cache PVC -> Liquidsoap -> FIFO -> FFmpeg -> HLS -> Nginx
                    queue-player -> Liquidsoap request.queue
                              API -> Nginx /api/
```

1. `alembic` Job применяет миграции из `alembic/versions`.
   Python не создает и не мигрирует таблицы, он только проверяет, что схема уже
   есть.
2. `search` запускает `python -m manager search`, ходит в YouTube Data API,
   получает метаданные и пишет треки в PostgreSQL через `TracksRepo.upsert()`.
   `yt-dlp` в поиске не используется. Итоговая YouTube API телеметрия пишется в
   `/opt/radio/runtime/info/youtube_api.json`.
3. `prefetch` запускает `python -m manager prefetch`, берет из PostgreSQL треки
   без `audio_path`, скачивает аудио через `yt-dlp`, меряет LUFS через FFmpeg,
   пишет файлы в `cache/cold`, поддерживает маленький рабочий набор свежих
   файлов в `cache/hot` и обновляет строку трека в PostgreSQL.
4. `liquidsoap` запускается напрямую как процесс `liquidsoap -v
   /opt/radio/data/radio.liq`. Внутри есть стандартный `request.queue` для
   ручной очереди и library-ротация: 1 трек из `cache/hot`, затем 4 трека из
   полного `cache/cold`. Очередь стоит выше library, но `track_sensitive=true`
   не обрывает текущий трек посреди композиции.
5. `queue-player` запускает `python -m manager queue-player`. Он берет
   `pending` строку из Postgres, переводит ее в `queued` и отправляет URI в
   Liquidsoap telnet-командой `request_queue.push`. Когда Liquidsoap пишет
   `queue_id` в `nowplaying.txt.kv`, строка становится `playing`; когда metadata
   возвращается к library без `queue_id`, строка становится `done`.
6. `ffmpeg` запускается через `python -m manager ffmpeg-hls`. Python только
   собирает аргументы из конфига и делает `execvp`, после чего внутри контейнера
   остается настоящий процесс `ffmpeg`. Он читает FIFO и пишет HLS TS/fMP4 в
   `/opt/radio/www/hls`.
7. `api` запускает `uvicorn manager.api:app` и дает тонкий HTTP-доступ к
   health/current/queue/offers/metrics. Мутации закрыты `Authorization: Bearer`
   токеном из `RADIO_ADMIN_TOKEN`. `/current` читает фактический
   `nowplaying.txt(.kv)` от Liquidsoap и отдает расчетный HLS offset,
   `/health` показывает состояние YouTube API quota/errors, `/metrics` отдает
   компактный JSON по трекам, очереди, текущему эфиру и YouTube API.
8. `nginx` отдает HLS из общего `emptyDir` volume и проксирует `/api/` в
   FastAPI-контейнер.
9. `postgres-backup` CronJob раз в сутки делает `pg_dump -Fc` в
   `radio-cache/postgres` и чистит дампы старше 14 дней.

Если падает `search`, `prefetch`, `api`, `liquidsoap`, `ffmpeg` или `nginx`, их
перезапускает kubelet. В коде больше нет `ControlBus`, `Runner`,
`ServiceRunnable` и subprocess-supervisor слоя.

## Где состояние

- PostgreSQL: треки, очередь, предложка и доменная модель.
- PVC `radio-cache`: скачанные аудиофайлы, blacklist скачивания и backup-дампы
  PostgreSQL.
- `emptyDir radio-runtime`: FIFO и runtime info, которые можно потерять при
  пересоздании pod. Здесь же лежат `nowplaying.txt(.kv)` и
  `youtube_api.json`.
- `emptyDir radio-www`: HLS сегменты, которые FFmpeg пересоздает.
- Kubernetes Secret: `RADIO_DATABASE_DSN`, `RADIO_YOUTUBE_API_KEY`,
  `RADIO_ADMIN_TOKEN` и параметры PostgreSQL.

Redis и RTMP-конфиг сейчас убраны: активный код их не использует. Их стоит
возвращать только под конкретную задачу, иначе это лишние контейнеры, секреты и
проверки.

## Готовые решения

Оставлено:

- Kubernetes Deployment/Pod вместо самописного runner.
- Kubernetes Job для Alembic.
- Kubernetes CronJob для простого `pg_dump`.
- PostgreSQL вместо SQLite.
- Alembic вместо Python-миграций на старте приложения.
- YouTube Data API для поиска и метаданных.
- Runtime JSON-файл для YouTube API telemetry вместо Redis/новой таблицы.
- `yt-dlp` только для скачивания аудио.
- FastAPI как тонкий HTTP-слой без управления процессами.
- Liquidsoap `request.queue`, FFmpeg и Nginx как готовые процессы. Python не
  управляет их lifecycle, а только вызывает telnet API очереди.

Не добавлено специально:

- CloudNativePG: полезен, когда нужны backup/restore/HA/failover. Для текущего
  одного Postgres это больше CRD и контроллеров, чем пользы.
- External Secrets Operator: нужен, когда есть Vault/AWS/GCP/Azure secret store.
  Сейчас обычного Kubernetes Secret меньше и понятнее.
- CronJob для `search`/`prefetch`: подойдет для редких batch-задач, но текущие
  workers держат горячий кеш постоянно и проще читаются как long-running
  containers.
- Redis: нет текущей задачи для lock/rate-limit/ephemeral state.

## Команды

```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
# edit deploy/k8s/secret.yaml locally; it is ignored by git
docker build -t radio-manager:latest -f docker/app/Dockerfile .
kubectl apply -k deploy
kubectl -n radio wait --for=condition=complete job/alembic --timeout=180s
```

Проверить сгенерированные манифесты:

```bash
kubectl kustomize deploy
```

## Где слушать

Service `radio` опубликован как `NodePort`, поэтому для локального Docker
Desktop port-forward не нужен:

```text
http://127.0.0.1:30080/hls/mp4/playlist.m3u8
http://127.0.0.1:30080/api/health
http://127.0.0.1:30080/api/current
http://127.0.0.1:30080/api/metrics
http://127.0.0.1:30080/api/admin
```

HLS лучше открывать в VLC/mpv. Браузер может не проигрывать `.m3u8` напрямую.
Админка использует `RADIO_ADMIN_TOKEN` из локального `deploy/k8s/secret.yaml`.

## Как смотреть БД

Самый простой способ без внешнего порта:

```bash
kubectl -n radio exec -it postgres-0 -- sh -lc 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

Для DBeaver/DataGrip поднимай временный port-forward:

```bash
kubectl -n radio port-forward svc/postgres 15432:5432
```

Параметры подключения бери из локального ignored-файла
`deploy/k8s/secret.yaml`.

## YouTube quota

`/api/health` показывает состояние YouTube Data API. Если там
`quota_exhausted: true`, поиск новых треков временно остановится на долгий
backoff, но уже скачанные треки продолжат играть.

## Backup и restore

Дампы лежат в PVC:

```bash
kubectl -n radio exec deploy/radio -c prefetch -- ls -lh /opt/radio/cache/postgres
```

Ручной backup без ожидания расписания:

```bash
kubectl -n radio create job --from=cronjob/postgres-backup postgres-backup-manual
```

Restore делай осознанно, когда приложение остановлено или ты точно понимаешь,
что перезаписываешь:

```bash
kubectl -n radio cp ./radio.dump postgres-0:/tmp/radio.dump
kubectl -n radio exec -it postgres-0 -- sh -lc 'pg_restore --clean --if-exists -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/radio.dump'
```
