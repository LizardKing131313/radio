from __future__ import annotations

# ruff: noqa: E501
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from hmac import compare_digest
from pathlib import Path as FsPath
from typing import Annotated, cast

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from manager.config import AppConfig, MissingConfigError, get_settings
from manager.now_playing import current_snapshot
from manager.playback.telnet import LiquidsoapTelnetClient, LiquidsoapTelnetError
from manager.search.telemetry import read_youtube_api_telemetry
from manager.track_queue.db import Database
from manager.track_queue.models import QueueItem, Track
from manager.track_queue.repo import OffersRepo, QueueRepo, TracksRepo


class EnqueueRequest(BaseModel):
    track_id: int = Field(gt=0)
    requested_by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OfferRequest(BaseModel):
    youtube_url: str = Field(min_length=1, max_length=2000)
    submitted_by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OfferAcceptRequest(BaseModel):
    track_id: int = Field(gt=0)


ADMIN_HTML = """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Radio Admin</title>
  <style>
    :root { color-scheme: only light; font-family: system-ui, sans-serif; }
    body { margin: 0; background: #f4f6f8; color: #16202a; }
    header { display: flex; gap: 12px; align-items: center; justify-content: space-between; padding: 14px 18px; background: #17212b; color: white; }
    main { padding: 16px; display: grid; gap: 14px; }
    section { background: #ffffff; border: 1px solid #d7dde3; border-radius: 6px; color: #16202a; padding: 12px; }
    h2 { margin: 0 0 10px; font-size: 16px; line-height: 1.3; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
    input, select, button { min-height: 34px; border: 1px solid #b9c2cc; border-radius: 4px; box-sizing: border-box; color: #111827; padding: 0 10px; font: inherit; }
    input, select { background: #ffffff; }
    button { background: #edf2f7; cursor: pointer; }
    button.primary { background: #155eef; border-color: #155eef; color: #ffffff; }
    button.danger { background: #b42318; border-color: #b42318; color: #ffffff; }
    a, a:visited { color: #174ea6; }
    table { width: 100%; border-collapse: collapse; color: #111827; font-size: 14px; }
    th, td { padding: 8px; border-bottom: 1px solid #e1e6eb; text-align: left; vertical-align: top; }
    th { background: #f8fafc; }
    .muted { color: #667085; }
    .status { display: flex; flex-wrap: wrap; gap: 12px; }
    .actions { display: flex; flex-wrap: wrap; gap: 6px; }
    .error { background: #fff4ed; border-color: #ffb088; color: #7a271a; }
    .notice { background: #ecfdf3; border-color: #73d19b; color: #074d31; }
    .empty { color: #667085; padding: 18px 8px; }
    @media (max-width: 760px) {
      header, .toolbar { align-items: stretch; flex-direction: column; }
      table, thead, tbody, th, td, tr { display: block; }
      thead { display: none; }
      tr { border-bottom: 1px solid #d7dde3; padding: 8px 0; }
      td { border: 0; padding: 4px 0; }
      td::before { content: attr(data-label); display: block; color: #667085; font-size: 12px; }
    }
  </style>
</head>
<body>
  <header>
    <strong>Radio Admin</strong>
    <div class="toolbar">
      <input id="token" type="password" placeholder="Admin token" autocomplete="current-password">
      <button id="saveToken">Сохранить</button>
      <button id="refresh" class="primary">Обновить</button>
    </div>
  </header>
  <main>
    <section class="status">
      <div><b>Сейчас:</b> <span id="current">...</span></div>
      <div><b>Очередь:</b> <span id="queue">...</span></div>
      <div><b>YouTube:</b> <span id="youtube">...</span></div>
      <div><b>Треки:</b> <span id="stats">...</span></div>
      <button id="skip" class="danger">Пропустить</button>
    </section>
    <section id="error" class="error" hidden></section>
    <section id="notice" class="notice" hidden></section>
    <section>
      <h2>Очередь эфира</h2>
      <table>
        <thead><tr><th>ID</th><th>Трек</th><th>Статус</th></tr></thead>
        <tbody id="queueItems"></tbody>
      </table>
    </section>
    <section>
      <h2>История очереди</h2>
      <table>
        <thead><tr><th>ID</th><th>Трек</th><th>Статус</th></tr></thead>
        <tbody id="historyItems"></tbody>
      </table>
    </section>
    <section>
      <div class="toolbar">
        <input id="query" placeholder="Поиск по названию, каналу, youtube id">
        <select id="status">
          <option value="downloaded">Скачанные</option>
          <option value="active">Активные</option>
          <option value="missing">Без аудио</option>
          <option value="failed">Ошибки</option>
          <option value="inactive">Отключенные</option>
          <option value="deleted">Забаненные</option>
          <option value="all">Все</option>
        </select>
        <button id="search">Найти</button>
      </div>
      <table>
        <thead><tr><th>ID</th><th>Трек</th><th>Состояние</th><th>Действия</th></tr></thead>
        <tbody id="tracks"></tbody>
      </table>
    </section>
  </main>
  <script>
    const api = location.pathname.startsWith('/api/') ? '/api' : '';
    const el = id => document.getElementById(id);
    el('token').value = localStorage.radioAdminToken || '';
    el('saveToken').onclick = () => { localStorage.radioAdminToken = el('token').value; load(); };
    el('refresh').onclick = () => load();
    el('search').onclick = () => loadTracks();
    el('skip').onclick = () => skipCurrent(el('skip'));
    el('query').onkeydown = event => { if (event.key === 'Enter') loadTracks(); };
    async function json(url, options = {}) {
      const response = await fetch(api + url, options);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }
    async function load() {
      clearError();
      clearNotice();
      const [currentResult, metricsResult] = await Promise.allSettled([json('/current'), json('/metrics')]);
      if (currentResult.status === 'fulfilled') {
        const src = currentResult.value.now_playing && currentResult.value.now_playing.source;
        el('current').textContent = src && src.line ? src.line : 'нет данных';
      } else {
        el('current').textContent = 'ошибка загрузки';
        setError(currentResult.reason);
      }
      if (metricsResult.status === 'fulfilled') {
        const metrics = metricsResult.value;
        const queue = metrics.queue || {};
        const items = Array.isArray(queue.visible) ? queue.visible : [];
        const history = Array.isArray(queue.history) ? queue.history : [];
        el('queue').textContent = items.length ? items.map(formatQueueItem).join(' | ') : 'пусто';
        el('youtube').textContent = formatYoutube(metrics.youtube_api || {});
        renderQueueTable('queueItems', items);
        renderQueueTable('historyItems', history);
      } else {
        el('queue').textContent = 'ошибка загрузки';
        el('youtube').textContent = 'ошибка загрузки';
        renderQueueTable('queueItems', []);
        renderQueueTable('historyItems', []);
        setError(metricsResult.reason);
      }
      await loadTracks();
    }
    async function loadTracks() {
      try {
        const params = new URLSearchParams({status: el('status').value, limit: '80'});
        if (el('query').value.trim()) params.set('q', el('query').value.trim());
        const data = await json('/tracks?' + params.toString());
        el('stats').textContent = Object.entries(data.stats || {}).map(([k, v]) => `${k}: ${v}`).join(', ') || 'нет данных';
        const items = Array.isArray(data.items) ? data.items : [];
        el('tracks').innerHTML = items.length ? items.map(row).join('') : '<tr><td class="empty" colspan="4">Нет треков по этому фильтру</td></tr>';
      } catch (error) {
        el('stats').textContent = 'ошибка загрузки';
        el('tracks').innerHTML = '<tr><td class="empty" colspan="4">Не удалось загрузить треки</td></tr>';
        setError(error);
      }
    }
    function row(track) {
      const state = `${track.cache_state || 'none'} / fails ${track.fail_count || 0}`;
      const title = escapeHtml(track.title || 'Без названия');
      const channel = escapeHtml(track.channel || '');
      const url = escapeAttr(track.url || `https://www.youtube.com/watch?v=${track.youtube_id || ''}`);
      return `<tr>
        <td data-label="ID">${track.id}<br><span class="muted">${escapeHtml(track.youtube_id)}</span></td>
        <td data-label="Трек"><b>${title}</b><br><span class="muted">${channel}</span></td>
        <td data-label="Состояние">${state}<br><span class="muted">${track.duration_sec}s</span></td>
        <td data-label="Действия" class="actions">
          <button onclick="enqueue(${track.id}, this)">В очередь</button>
          <button class="primary" onclick="playNow(${track.id}, this)">Сейчас</button>
          <button onclick="retryTrack(${track.id}, this)">Перекачать</button>
          ${track.deleted_at ? `<button onclick="restoreTrack(${track.id}, this)">Вернуть</button>` : `<button class="danger" onclick="banTrack(${track.id}, this)">Бан</button>`}
          <a href="${url}" target="_blank" rel="noreferrer"><button>YT</button></a>
        </td>
      </tr>`;
    }
    async function enqueue(trackId, button) {
      await runAction(button, 'Добавлено в очередь', async () => {
        await json('/queue/append/admin', {method: 'POST', headers: authJson(), body: JSON.stringify({track_id: trackId})});
      });
    }
    async function playNow(trackId, button) {
      await runAction(button, 'Запущено сейчас', async () => {
        await json(`/tracks/${trackId}/play-now`, {method: 'POST', headers: auth()});
      });
    }
    async function skipCurrent(button) {
      await runAction(button, 'Текущий эфир пропущен', async () => {
        await json('/queue/skip', {method: 'POST', headers: auth()});
      });
    }
    async function banTrack(trackId, button) {
      await runAction(button, 'Трек забанен', async () => {
        await json(`/tracks/${trackId}/ban`, {method: 'POST', headers: auth()});
      });
    }
    async function restoreTrack(trackId, button) {
      await runAction(button, 'Трек возвращен', async () => {
        await json(`/tracks/${trackId}/restore`, {method: 'POST', headers: auth()});
      });
    }
    async function retryTrack(trackId, button) {
      await runAction(button, 'Скачивание запланировано заново', async () => {
        await json(`/tracks/${trackId}/retry`, {method: 'POST', headers: auth()});
      });
    }
    async function runAction(button, message, task) {
      try {
        clearError();
        clearNotice();
        setBusy(button, true);
        await task();
        await load();
        setNotice(message);
      } catch (error) {
        setError(error);
      } finally {
        setBusy(button, false);
      }
    }
    function authJson() {
      return {'Content-Type': 'application/json', ...auth()};
    }
    function setBusy(button, busy) {
      if (button) button.disabled = busy;
    }
    function requireToken() {
      const token = (el('token').value || localStorage.radioAdminToken || '').trim();
      if (!token) throw new Error('Введите admin token');
      localStorage.radioAdminToken = token;
      return token;
    }
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[ch]));
    }
    function formatQueueItem(item) {
      const queueItem = item.queue_item || {};
      const track = item.track || {};
      return `${queueItem.status || '?'}: ${track.title || track.youtube_id || track.id || '?'}`;
    }
    function renderQueueTable(target, items) {
      el(target).innerHTML = items.length ? items.map(queueRow).join('') : '<tr><td class="empty" colspan="3">Пусто</td></tr>';
    }
    function queueRow(item) {
      const queueItem = item.queue_item || {};
      const track = item.track || {};
      const detail = queueItem.error_detail ? `<br><span class="muted">${escapeHtml(queueItem.error_detail)}</span>` : '';
      return `<tr>
        <td data-label="ID">${queueItem.id || ''}</td>
        <td data-label="Трек"><b>${escapeHtml(track.title || 'Без названия')}</b><br><span class="muted">${escapeHtml(track.youtube_id || '')}</span></td>
        <td data-label="Статус">${escapeHtml(queueItem.status || '?')}${detail}</td>
      </tr>`;
    }
    function formatYoutube(telemetry) {
      const status = telemetry.quota_exhausted ? 'квота закончилась' : (telemetry.status || 'нет данных');
      const errors = telemetry.consecutive_errors ?? 0;
      const units = telemetry.estimated_quota_units ?? 0;
      return `${status}; ошибок подряд: ${errors}; units: ${units}`;
    }
    function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }
    function auth() { return {'Authorization': 'Bearer ' + requireToken()}; }
    function setError(error) {
      const box = el('error');
      box.hidden = false;
      box.textContent = String(error && error.message ? error.message : error);
    }
    function clearError() {
      const box = el('error');
      box.hidden = true;
      box.textContent = '';
    }
    function setNotice(message) {
      const box = el('notice');
      box.hidden = false;
      box.textContent = message;
    }
    function clearNotice() {
      const box = el('notice');
      box.hidden = true;
      box.textContent = '';
    }
    load();
  </script>
</body>
</html>
"""


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database()
    app.state.database = database
    try:
        yield
    finally:
        database.close()


app = FastAPI(title="radio-manager", lifespan=lifespan)


def get_database(request: Request) -> Database:
    return request.app.state.database


DatabaseDep = Annotated[Database, Depends(get_database)]


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    # Мутации закрыты одним token из Kubernetes Secret. Сложнее auth добавим,
    # когда появится реальная внешняя админка.
    try:
        expected = get_settings().secrets.admin_token.get_secret_value()
    except MissingConfigError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin token is not configured",
        ) from exception

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@app.get("/health")
def health(database: DatabaseDep) -> dict[str, object]:
    database.ensure_schema()
    settings = get_settings()
    return {
        "status": "ok",
        "youtube_api": read_youtube_api_telemetry(settings.paths.youtube_telemetry_path),
    }


@app.get("/admin", response_class=HTMLResponse)
def admin_page() -> HTMLResponse:
    return HTMLResponse(ADMIN_HTML, headers={"Cache-Control": "no-store"})


@app.get("/current")
def current(database: DatabaseDep) -> dict[str, object | None]:
    settings = get_settings()
    current_item = QueueRepo(database).current_playing()
    return {
        "now_playing": current_snapshot(settings),
        "queue": _queue_entry(current_item) if current_item is not None else None,
    }


@app.get("/metrics")
def metrics(database: DatabaseDep) -> dict[str, object]:
    settings = get_settings()
    return _runtime_metrics(database, settings)


@app.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus(database: DatabaseDep) -> PlainTextResponse:
    settings = get_settings()
    text = _prometheus_text(_runtime_metrics(database, settings))
    return PlainTextResponse(
        text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def _runtime_metrics(database: Database, settings: AppConfig) -> dict[str, object]:
    queue_repo = QueueRepo(database)
    return {
        "status": "ok",
        "tracks": TracksRepo(database).stats(),
        "queue": {
            "visible": [_queue_entry(item) for item in queue_repo.list_visible(limit=50)],
            "history": [_queue_entry(item) for item in queue_repo.history(limit=20)],
        },
        "current": current_snapshot(settings),
        "youtube_api": read_youtube_api_telemetry(settings.paths.youtube_telemetry_path),
    }


def _prometheus_text(snapshot: dict[str, object]) -> str:
    tracks = cast(dict[str, int], snapshot["tracks"])
    queue = cast(dict[str, list[dict[str, object]]], snapshot["queue"])
    current = cast(dict[str, object], snapshot["current"])
    youtube_api = cast(dict[str, object], snapshot["youtube_api"])
    hls = cast(dict[str, object], current["hls"])
    visible = queue["visible"]
    history = queue["history"]

    # Prometheus endpoint намеренно строится из того же snapshot, что и JSON /metrics.
    # Так мониторинг и человек в админке смотрят на один источник правды.
    lines = [
        "# HELP radio_tracks_total Количество треков по статусам каталога.",
        "# TYPE radio_tracks_total gauge",
    ]
    for status_name, count in sorted(tracks.items()):
        lines.append(
            f'radio_tracks_total{{status="{_prometheus_label(str(status_name))}"}} {int(count)}'
        )
    lines.extend(
        [
            "# HELP radio_queue_visible_items Видимые элементы ручной очереди.",
            "# TYPE radio_queue_visible_items gauge",
            f"radio_queue_visible_items {len(visible)}",
            "# HELP radio_queue_history_items Завершенные элементы ручной очереди.",
            "# TYPE radio_queue_history_items gauge",
            f"radio_queue_history_items {len(history)}",
            "# HELP radio_youtube_quota_exhausted YouTube Data API вернул quota/rate limit.",
            "# TYPE radio_youtube_quota_exhausted gauge",
            f"radio_youtube_quota_exhausted {int(bool(youtube_api.get('quota_exhausted')))}",
            "# HELP radio_youtube_consecutive_errors Подряд идущие ошибки YouTube Data API.",
            "# TYPE radio_youtube_consecutive_errors gauge",
            f"radio_youtube_consecutive_errors {int(cast(int | None, youtube_api.get('consecutive_errors')) or 0)}",
            "# HELP radio_youtube_estimated_quota_units_total Оценка потраченных quota units.",
            "# TYPE radio_youtube_estimated_quota_units_total counter",
            f"radio_youtube_estimated_quota_units_total {int(cast(int | None, youtube_api.get('estimated_quota_units')) or 0)}",
            "# HELP radio_hls_live_offset_seconds Расчетное отставание HLS от live edge.",
            "# TYPE radio_hls_live_offset_seconds gauge",
            f"radio_hls_live_offset_seconds {int(cast(int | None, hls.get('live_offset_sec')) or 0)}",
            "# HELP radio_hls_nowplaying_age_seconds Возраст последнего nowplaying от Liquidsoap.",
            "# TYPE radio_hls_nowplaying_age_seconds gauge",
            f"radio_hls_nowplaying_age_seconds {int(cast(int | None, hls.get('age_sec')) or 0)}",
        ]
    )
    return "\n".join(lines) + "\n"


def _prometheus_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


@app.get("/queue")
def queue(
    database: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, list[dict[str, object]]]:
    items = QueueRepo(database).list_visible(limit=limit)
    return {"items": [_queue_entry(item) for item in items]}


@app.get("/tracks")
def tracks(
    database: DatabaseDep,
    q: Annotated[str | None, Query(max_length=200)] = None,
    status_filter: Annotated[str, Query(alias="status")] = "active",
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, object]:
    repo = TracksRepo(database)
    try:
        items = repo.list_tracks(query=q, status=status_filter, limit=limit)
        stats = repo.stats()
    except ValueError as exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exception)) from (
            exception
        )
    return {"items": [dict(track.to_dict()) for track in items], "stats": stats}


@app.post("/tracks/{track_id}/ban", dependencies=[Depends(require_admin_token)])
def track_ban(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    track = _get_track_or_404(repo, track_id)
    _remove_track_files(track, get_settings())
    return {"status": "banned", "track": dict(repo.ban(track_id).to_dict())}


@app.post("/tracks/{track_id}/restore", dependencies=[Depends(require_admin_token)])
def track_restore(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    _get_track_or_404(repo, track_id)
    return {"status": "restored", "track": dict(repo.restore(track_id).to_dict())}


@app.post("/tracks/{track_id}/retry", dependencies=[Depends(require_admin_token)])
def track_retry(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    track = _get_track_or_404(repo, track_id)
    _remove_track_files(track, get_settings())
    return {"status": "scheduled", "track": dict(repo.retry_download(track_id).to_dict())}


@app.post("/tracks/{track_id}/play-now", dependencies=[Depends(require_admin_token)])
def track_play_now(track_id: int, database: DatabaseDep) -> dict[str, object]:
    tracks_repo = TracksRepo(database)
    queue_repo = QueueRepo(database)
    track = _get_track_or_404(tracks_repo, track_id)
    path = _playable_audio_path(track)
    client = LiquidsoapTelnetClient()
    try:
        # "Играть сейчас" не создает queue_items. Сначала чистим уже отправленные
        # request.queue items, потом кладем прямой request и скипаем текущий output.
        client.flush_request_queue()
        client.push_request(_direct_play_uri(track, path))
        client.skip_output()
    except LiquidsoapTelnetError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"liquidsoap command failed: {exception}",
        ) from exception

    skipped_queue_items = queue_repo.skip_current()
    tracks_repo.touch_play(track.id)
    return {
        "status": "playing",
        "skipped_queue_items": skipped_queue_items,
        "track": dict(tracks_repo.get(track.id).to_dict()),
    }


@app.post("/queue/append", dependencies=[Depends(require_admin_token)])
def queue_append(
    payload: EnqueueRequest,
    database: DatabaseDep,
) -> dict[str, int]:
    queue_id = QueueRepo(database).enqueue(
        payload.track_id,
        requested_by=payload.requested_by,
        note=payload.note,
    )
    return {"queue_id": queue_id}


@app.post("/queue/append/admin", dependencies=[Depends(require_admin_token)])
def queue_append_admin(
    payload: EnqueueRequest,
    database: DatabaseDep,
) -> dict[str, int]:
    queue_id = QueueRepo(database).enqueue_next(
        payload.track_id,
        requested_by=payload.requested_by,
        note=payload.note,
    )
    return {"queue_id": queue_id}


@app.post("/queue/skip", dependencies=[Depends(require_admin_token)])
def queue_skip(database: DatabaseDep) -> dict[str, object]:
    queue_repo = QueueRepo(database)
    active = queue_repo.current_active()
    client = LiquidsoapTelnetClient()
    try:
        if active is not None and active[0].status == "queued":
            client.flush_request_queue()
        else:
            client.skip_output()
    except LiquidsoapTelnetError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"liquidsoap command failed: {exception}",
        ) from exception
    return {"status": "skipped", "queue_items": queue_repo.skip_current()}


@app.get("/offers")
def offers(
    database: DatabaseDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, list[dict[str, object]]]:
    items = OffersRepo(database).list(status=status_filter, limit=limit)
    return {"items": [dict(offer.to_dict()) for offer in items]}


@app.post("/offers/add")
def offers_add(
    payload: OfferRequest,
    database: DatabaseDep,
) -> dict[str, int]:
    offer_id = OffersRepo(database).add(
        payload.youtube_url,
        submitted_by=payload.submitted_by,
        note=payload.note,
    )
    return {"offer_id": offer_id}


@app.get("/offers/{offer_id}")
def offer(offer_id: int, database: DatabaseDep) -> dict[str, object]:
    try:
        item = OffersRepo(database).get(offer_id)
    except KeyError as exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="offer not found",
        ) from exception
    return dict(item.to_dict())


@app.post("/offers/{offer_id}/accept", dependencies=[Depends(require_admin_token)])
def offer_accept(
    offer_id: int,
    payload: OfferAcceptRequest,
    database: DatabaseDep,
) -> dict[str, str]:
    OffersRepo(database).accept(offer_id, payload.track_id)
    return {"status": "accepted"}


@app.post("/offers/{offer_id}/cancel", dependencies=[Depends(require_admin_token)])
def offer_cancel(
    offer_id: int,
    database: DatabaseDep,
) -> dict[str, str]:
    OffersRepo(database).cancel(offer_id)
    return {"status": "cancelled"}


def _queue_entry(item: tuple[QueueItem, Track]) -> dict[str, object]:
    queue_item, track = item
    return {"queue_item": dict(queue_item.to_dict()), "track": dict(track.to_dict())}


def _get_track_or_404(repo: TracksRepo, track_id: int) -> Track:
    try:
        return repo.get(track_id)
    except KeyError as exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="track not found",
        ) from exception


def _remove_track_files(track: Track, config: AppConfig) -> None:
    # API-контейнер монтирует тот же cache PVC. При бане/перекачке удаляем файл
    # из hot/cold, иначе Liquidsoap может продолжить брать старый .opus с диска.
    candidates = {
        config.paths.cache_cold / f"{track.youtube_id}.opus",
        config.paths.cache_hot / f"{track.youtube_id}.opus",
    }
    if track.audio_path:
        candidates.add(FsPath(track.audio_path))
    cache_roots = (config.paths.cache_cold, config.paths.cache_hot)
    for path in candidates:
        if _is_under_any(path, cache_roots):
            _unlink_if_exists(path)


def _is_under_any(path: FsPath, roots: tuple[FsPath, FsPath]) -> bool:
    resolved = path.resolve(strict=False)
    return any(resolved.is_relative_to(root.resolve(strict=False)) for root in roots)


def _unlink_if_exists(path: FsPath) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def _playable_audio_path(track: Track) -> FsPath:
    if track.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="track is deleted",
        )
    if not track.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="track is inactive",
        )
    if not track.audio_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="track is not downloaded",
        )
    path = FsPath(track.audio_path)
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="track audio file is missing",
        )
    return path


def _direct_play_uri(track: Track, path: FsPath) -> str:
    normalized = str(path).replace("\\", "/")
    return f'annotate:track_id="{track.id}":{normalized}'
