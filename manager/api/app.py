from __future__ import annotations

# ruff: noqa: E501
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress
from hmac import compare_digest
from pathlib import Path as FsPath
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
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
    const auth = () => ({'Authorization': 'Bearer ' + localStorage.radioAdminToken});
    el('token').value = localStorage.radioAdminToken || '';
    el('saveToken').onclick = () => { localStorage.radioAdminToken = el('token').value; load(); };
    el('refresh').onclick = () => load();
    el('search').onclick = () => loadTracks();
    el('skip').onclick = () => skipCurrent();
    el('query').onkeydown = event => { if (event.key === 'Enter') loadTracks(); };
    async function json(url, options = {}) {
      const response = await fetch(api + url, options);
      if (!response.ok) throw new Error(await response.text());
      return response.json();
    }
    async function load() {
      clearError();
      const [healthResult, currentResult, queueResult] = await Promise.allSettled([json('/health'), json('/current'), json('/queue?limit=5')]);
      if (currentResult.status === 'fulfilled') {
        const src = currentResult.value.now_playing && currentResult.value.now_playing.source;
        el('current').textContent = src && src.line ? src.line : 'нет данных';
      } else {
        el('current').textContent = 'ошибка загрузки';
        setError(currentResult.reason);
      }
      if (healthResult.status === 'fulfilled') {
        const telemetry = healthResult.value.youtube_api || {};
        el('youtube').textContent = telemetry.quota_exhausted ? 'quota exceeded' : (telemetry.status || 'нет данных');
      } else {
        el('youtube').textContent = 'ошибка загрузки';
        setError(healthResult.reason);
      }
      if (queueResult.status === 'fulfilled') {
        const items = Array.isArray(queueResult.value.items) ? queueResult.value.items : [];
        el('queue').textContent = items.length ? items.map(formatQueueItem).join(' | ') : 'пусто';
      } else {
        el('queue').textContent = 'ошибка загрузки';
        setError(queueResult.reason);
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
          <button onclick="enqueue(${track.id})">В очередь</button>
          <button onclick="retryTrack(${track.id})">Перекачать</button>
          ${track.deleted_at ? `<button onclick="restoreTrack(${track.id})">Вернуть</button>` : `<button class="danger" onclick="banTrack(${track.id})">Бан</button>`}
          <a href="${url}" target="_blank" rel="noreferrer"><button>YT</button></a>
        </td>
      </tr>`;
    }
    async function enqueue(trackId) {
      await json('/queue/append/admin', {method: 'POST', headers: {'Content-Type': 'application/json', ...auth()}, body: JSON.stringify({track_id: trackId})});
      await load();
    }
    async function skipCurrent() {
      await json('/queue/skip', {method: 'POST', headers: auth()});
      await load();
    }
    async function banTrack(trackId) {
      await json(`/tracks/${trackId}/ban`, {method: 'POST', headers: auth()});
      await loadTracks();
    }
    async function restoreTrack(trackId) {
      await json(`/tracks/${trackId}/restore`, {method: 'POST', headers: auth()});
      await loadTracks();
    }
    async function retryTrack(trackId) {
      await json(`/tracks/${trackId}/retry`, {method: 'POST', headers: auth()});
      await loadTracks();
    }
    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;', "'":'&#39;'}[ch]));
    }
    function formatQueueItem(item) {
      const queueItem = item.queue_item || {};
      const track = item.track || {};
      return `${queueItem.status || '?'}: ${track.title || track.youtube_id || track.id || '?'}`;
    }
    function escapeAttr(value) { return escapeHtml(value).replace(/`/g, '&#96;'); }
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
