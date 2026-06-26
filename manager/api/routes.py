from __future__ import annotations

# ruff: noqa: E501
from contextlib import suppress
from pathlib import Path as FsPath
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from manager.api.dependencies import DatabaseDep, require_admin_token
from manager.api.schemas import EnqueueRequest, OfferAcceptRequest, OfferRequest
from manager.api.serializers import queue_entry
from manager.config import AppConfig, get_settings
from manager.now_playing import current_snapshot
from manager.playback.queue_player import read_queue_metadata
from manager.playback.telnet import LiquidsoapTelnetClient, LiquidsoapTelnetError
from manager.search.telemetry import read_youtube_api_telemetry
from manager.track_queue.db import Database
from manager.track_queue.models import Track
from manager.track_queue.repo import OffersRepo, QueueRepo, TracksRepo

router = APIRouter()


@router.get("/health")
def health(database: DatabaseDep) -> dict[str, object]:
    database.ensure_schema()
    settings = get_settings()
    return {
        "status": "ok",
        "youtube_api": read_youtube_api_telemetry(settings.paths.youtube_telemetry_path),
    }


@router.get("/current")
def current(database: DatabaseDep) -> dict[str, object | None]:
    settings = get_settings()
    current_item = QueueRepo(database).current_playing()
    return {
        "now_playing": current_snapshot(settings),
        "queue": queue_entry(current_item) if current_item is not None else None,
    }


@router.get("/metrics")
def metrics(database: DatabaseDep) -> dict[str, object]:
    settings = get_settings()
    return runtime_metrics(database, settings)


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
def metrics_prometheus(database: DatabaseDep) -> PlainTextResponse:
    settings = get_settings()
    text = prometheus_text(runtime_metrics(database, settings))
    return PlainTextResponse(
        text,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


def runtime_metrics(database: Database, settings: AppConfig) -> dict[str, object]:
    queue_repo = QueueRepo(database)
    return {
        "status": "ok",
        "tracks": TracksRepo(database).stats(),
        "queue": {
            "visible": [queue_entry(item) for item in queue_repo.list_visible(limit=50)],
            "history": [queue_entry(item) for item in queue_repo.history(limit=20)],
        },
        "current": current_snapshot(settings),
        "youtube_api": read_youtube_api_telemetry(settings.paths.youtube_telemetry_path),
    }


def prometheus_text(snapshot: dict[str, object]) -> str:
    tracks = cast(dict[str, int], snapshot["tracks"])
    queue = cast(dict[str, list[dict[str, object]]], snapshot["queue"])
    current_data = cast(dict[str, object], snapshot["current"])
    youtube_api = cast(dict[str, object], snapshot["youtube_api"])
    hls = cast(dict[str, object], current_data["hls"])
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
            f'radio_tracks_total{{status="{prometheus_label(str(status_name))}"}} {int(count)}'
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


def prometheus_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


@router.get("/queue")
def queue(
    database: DatabaseDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> dict[str, list[dict[str, object]]]:
    items = QueueRepo(database).list_visible(limit=limit)
    return {"items": [queue_entry(item) for item in items]}


@router.get("/tracks")
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


@router.post("/tracks/{track_id}/ban", dependencies=[Depends(require_admin_token)])
def track_ban(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    track = get_track_or_404(repo, track_id)
    remove_track_files(track, get_settings())
    return {"status": "banned", "track": dict(repo.ban(track_id).to_dict())}


@router.post("/tracks/{track_id}/restore", dependencies=[Depends(require_admin_token)])
def track_restore(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    get_track_or_404(repo, track_id)
    return {"status": "restored", "track": dict(repo.restore(track_id).to_dict())}


@router.post("/tracks/{track_id}/retry", dependencies=[Depends(require_admin_token)])
def track_retry(track_id: int, database: DatabaseDep) -> dict[str, object]:
    repo = TracksRepo(database)
    track = get_track_or_404(repo, track_id)
    remove_track_files(track, get_settings())
    return {"status": "scheduled", "track": dict(repo.retry_download(track_id).to_dict())}


@router.post("/tracks/{track_id}/play-now", dependencies=[Depends(require_admin_token)])
def track_play_now(track_id: int, database: DatabaseDep) -> dict[str, object]:
    tracks_repo = TracksRepo(database)
    queue_repo = QueueRepo(database)
    track = get_track_or_404(tracks_repo, track_id)
    path = playable_audio_path(track)
    queue_id, skipped_queue_items = queue_repo.enqueue_immediate(
        track.id,
        requested_by="admin",
        note="play-now",
    )
    client = LiquidsoapTelnetClient()
    try:
        play_immediately(client, queued_play_uri(queue_id, track, path, queue_kind="urgent"))
    except LiquidsoapTelnetError as exception:
        queue_repo.mark_failed(queue_id, f"liquidsoap command failed: {exception}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"liquidsoap command failed: {exception}",
        ) from exception

    return {
        "status": "playing",
        "queue_id": queue_id,
        "skipped_queue_items": skipped_queue_items,
        "track": dict(tracks_repo.get(track.id).to_dict()),
    }


@router.post("/queue/append", dependencies=[Depends(require_admin_token)])
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


@router.post("/queue/append/admin", dependencies=[Depends(require_admin_token)])
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


@router.post("/queue/skip", dependencies=[Depends(require_admin_token)])
def queue_skip(database: DatabaseDep) -> dict[str, object]:
    queue_repo = QueueRepo(database)
    settings = get_settings()
    current_metadata = read_queue_metadata(settings.paths.nowplaying_path)
    active = queue_repo.current_active()
    client = LiquidsoapTelnetClient()
    skipped_queue_items = 0
    try:
        if current_metadata.queue_id is not None:
            if current_metadata.queue_kind == "urgent":
                client.skip_play_now()
            else:
                client.skip_request_queue()
            skipped_queue_items = queue_repo.skip_current(queue_id=current_metadata.queue_id)
        elif active is not None and current_metadata.track_id == active[1].id:
            client.skip_request_queue()
            skipped_queue_items = queue_repo.skip_current()
        else:
            client.skip_output()
            client.skip_library_sources()
            if active is not None and active[0].status == "playing":
                skipped_queue_items = queue_repo.skip_current()
    except LiquidsoapTelnetError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"liquidsoap command failed: {exception}",
        ) from exception
    return {"status": "skipped", "queue_items": skipped_queue_items}


@router.get("/offers")
def offers(
    database: DatabaseDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> dict[str, list[dict[str, object]]]:
    items = OffersRepo(database).list(status=status_filter, limit=limit)
    return {"items": [cast(dict[str, object], offer.to_dict()) for offer in items]}


@router.post("/offers/add")
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


@router.get("/offers/{offer_id}")
def offer(offer_id: int, database: DatabaseDep) -> dict[str, object]:
    try:
        item = OffersRepo(database).get(offer_id)
    except KeyError as exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="offer not found",
        ) from exception
    return dict(item.to_dict())


@router.post("/offers/{offer_id}/accept", dependencies=[Depends(require_admin_token)])
def offer_accept(
    offer_id: int,
    payload: OfferAcceptRequest,
    database: DatabaseDep,
) -> dict[str, str]:
    OffersRepo(database).accept(offer_id, payload.track_id)
    return {"status": "accepted"}


@router.post("/offers/{offer_id}/cancel", dependencies=[Depends(require_admin_token)])
def offer_cancel(
    offer_id: int,
    database: DatabaseDep,
) -> dict[str, str]:
    OffersRepo(database).cancel(offer_id)
    return {"status": "cancelled"}


def get_track_or_404(repo: TracksRepo, track_id: int) -> Track:
    try:
        return repo.get(track_id)
    except KeyError as exception:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="track not found",
        ) from exception


def remove_track_files(track: Track, config: AppConfig) -> None:
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
        if is_under_any(path, cache_roots):
            unlink_if_exists(path)


def is_under_any(path: FsPath, roots: tuple[FsPath, FsPath]) -> bool:
    resolved = path.resolve(strict=False)
    return any(resolved.is_relative_to(root.resolve(strict=False)) for root in roots)


def unlink_if_exists(path: FsPath) -> None:
    with suppress(OSError):
        path.unlink(missing_ok=True)


def playable_audio_path(track: Track) -> FsPath:
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


def queued_play_uri(
    queue_id: int,
    track: Track,
    path: FsPath,
    *,
    queue_kind: str | None = None,
) -> str:
    normalized = str(path).replace("\\", "/")
    annotations = [f'queue_id="{queue_id}"', f'track_id="{track.id}"']
    if queue_kind is not None:
        annotations.append(f'queue_kind="{queue_kind}"')
    return f"annotate:{','.join(annotations)}:{normalized}"


def play_immediately(client: LiquidsoapTelnetClient, uri: str) -> None:
    client.flush_request_queue()
    client.flush_play_now()
    client.push_play_now(uri)
