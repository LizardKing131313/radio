# Техдолг

## Активно

- Добавлять Redis только там, где он реально убирает проблему состояния. Хорошие кандидаты: короткие lock-и, rate limit
  и временный кеш текущего трека. Не использовать Redis как источник истины для очереди или предложек.
- Заменить старые systemd/shell deploy-доки после того, как Kubernetes-путь будет проверен на целевом хосте.
- Добавлять YouTube Live RTMP только когда будет реализован сам push потока. До этого не держать stream keys в конфиге и
  манифестах.
- Если локального `pg_dump` на PVC станет мало, заменить самописный CronJob на Postgres-оператор с нормальным
  backup/restore lifecycle.
- Если админка станет внешней публичной панелью, заменить один bearer token на нормальную auth-схему и audit log.

## Сделано

- Перенесено постоянное хранение очереди, каталога и предложек с SQLite на PostgreSQL.
- Владение схемой БД перенесено из встроенных Python-миграций в Alembic.
- Ручной SQL в репозиториях заменен на SQLAlchemy ORM для обычных чтений и записей приложения.
- `yt-dlp` убран из поиска. Он остался только в пути скачивания аудио.
- Добавлены Kubernetes-манифесты для Postgres, Alembic migration job, приложения и Nginx sidecar.
- Убран Python runner как активный оркестратор процессов. Kubernetes теперь запускает и перезапускает search, prefetch,
  Liquidsoap, FFmpeg и Nginx как контейнеры.
- Убраны неиспользуемые Redis и RTMP-конфиги из активного деплоя.
- Добавлено тонкое FastAPI-приложение для health, current, queue и offers endpoints.
- Добавлена admin-авторизация через bearer token для мутаций очереди и предложек.
- Добавлен CI integration target, который применяет Alembic к реальному PostgreSQL-контейнеру.
- Убраны пустые legacy Python entry files.
- Реализован `/current` на основе Liquidsoap `nowplaying.txt(.kv)` с расчетным HLS live offset.
- Добавлена телеметрия quota/error для YouTube API в runtime info, она отдается через `/health`.
- Закоммиченный Kubernetes Secret заменен на ignored локальный `secret.yaml`; в репе оставлен `secret.example.yaml`.
- Очередь из админки подключена к реальному эфиру через стандартный Liquidsoap `request.queue`; Python больше не
  изображает аудио-оркестратор.
- Добавлен `queue-player` worker: Postgres `pending/queued/playing` синхронизируется с Liquidsoap metadata.
- Добавлен `/metrics` с компактным JSON по трекам, очереди, текущему эфиру и YouTube API.
- Добавлен admin skip текущего эфира через Liquidsoap telnet API.
- Добавлен минимальный Kubernetes CronJob для `pg_dump -Fc`.
- В Docker-образ добавлен Node.js как JS runtime для `yt-dlp`, чтобы уменьшить отказы на YouTube player challenge.
