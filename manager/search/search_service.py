from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.search.search_helpers import YouTubeAPIError, search_title_page
from manager.search.telemetry import (
    estimate_window_quota_units,
    is_youtube_quota_error,
    read_youtube_api_telemetry,
    record_youtube_api_error,
    record_youtube_api_success,
)
from manager.track_queue.db import Database
from manager.track_queue.repo import TracksRepo


async def run_search_loop(config: AppConfig | None = None) -> None:
    cfg = config or get_settings()
    log = get_logger("search")
    database = Database(app_config=cfg)
    database.ensure_schema()
    tracks_repo = TracksRepo(database)

    # Цикл специально простой: Kubernetes перезапускает контейнер, а Postgres
    # дедуплицирует треки по youtube_id через TracksRepo.upsert().
    startup_sleep_sec = _startup_sleep_sec(cfg)
    if startup_sleep_sec > 0:
        log.info("search startup delayed by telemetry", sleep_sec=startup_sleep_sec)
        await asyncio.sleep(startup_sleep_sec)

    while True:
        sleep_sec = _next_sleep_sec(cfg)
        try:
            upserted = await search_once(cfg, tracks_repo, log)
            log.info("search tick ok", upserted=upserted)
        except YouTubeAPIError as exception:
            record_youtube_api_error(cfg.paths.youtube_telemetry_path, exception)
            sleep_sec = _next_sleep_sec(cfg, exception)
            log.warning("youtube api failed", error=str(exception), retry_after_sec=sleep_sec)
        except Exception as exception:
            log.warning("search tick failed", error=str(exception))
        await asyncio.sleep(sleep_sec)


async def search_once(config: AppConfig, tracks_repo: TracksRepo, log: FilteringBoundLogger) -> int:
    api_key = config.secrets.youtube_api_key.get_secret_value()
    upserted = 0
    page_token = _next_page_token(read_youtube_api_telemetry(config.paths.youtube_telemetry_path))
    window_size = _window_size(config.search.window_size)

    stop_search = False
    for window_index in range(max(1, config.search.max_windows_per_tick)):
        remaining_results = window_size
        while remaining_results > 0:
            # YouTube search.list отдает максимум 50 результатов за запрос, поэтому
            # configured window может занимать несколько API pages.
            page_size = _page_size(remaining_results)
            page = await asyncio.get_running_loop().run_in_executor(
                None,
                search_title_page,
                config.search.title,
                api_key,
                page_size,
                page_token,
            )
            record_youtube_api_success(
                config.paths.youtube_telemetry_path,
                estimated_quota_units=estimate_window_quota_units(page_size),
                result_count=len(page.tracks),
                next_page_token=page.next_page_token,
            )
            log.debug(
                "search page done",
                window_index=window_index,
                page_size=page_size,
                raw_count=page.raw_count,
                accepted=len(page.tracks),
                has_next_page=page.next_page_token is not None,
            )
            if page.raw_count == 0:
                stop_search = True
                break

            for track in page.tracks:
                youtube_id = str(track["youtube_id"])
                tracks_repo.upsert(
                    youtube_id=youtube_id,
                    title=str(track["title"]),
                    duration_sec=int(track["duration_sec"]),
                    url=track.get("url"),
                    channel=track.get("channel"),
                    thumbnail_url=track.get("thumbnail_url"),
                )
                upserted += 1

            remaining_results -= page_size
            page_token = page.next_page_token
            if page_token is None:
                stop_search = True
                break

        if stop_search:
            break

    log.debug("search once done", upserted=upserted)
    return upserted


def _next_sleep_sec(config: AppConfig, error: BaseException | None = None) -> int:
    # При quotaExceeded нет смысла дергать YouTube каждую минуту: квота от этого
    # не восстановится, а логи и лимиты будут забиваться дальше.
    interval_sec = max(1, config.search.interval_sec)
    if error is not None and is_youtube_quota_error(error):
        return max(interval_sec, config.search.quota_backoff_sec)
    return interval_sec


def _startup_sleep_sec(config: AppConfig, *, now: datetime | None = None) -> int:
    state = read_youtube_api_telemetry(config.paths.youtube_telemetry_path)
    timestamp = now or datetime.now(UTC)
    delays = [
        _remaining_sleep_sec(
            _parse_telemetry_time(state.get("last_success_at")),
            max(1, config.search.interval_sec),
            timestamp,
        )
    ]
    if state.get("quota_exhausted") is True:
        delays.append(
            _remaining_sleep_sec(
                _parse_telemetry_time(state.get("last_error_at")),
                max(max(1, config.search.interval_sec), config.search.quota_backoff_sec),
                timestamp,
            )
        )
    return max(delays)


def _remaining_sleep_sec(last_event_at: datetime | None, interval_sec: int, now: datetime) -> int:
    if last_event_at is None:
        return 0
    elapsed = (now - last_event_at).total_seconds()
    return max(0, math.ceil(interval_sec - elapsed))


def _parse_telemetry_time(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.removesuffix("Z")
    if normalized != value:
        normalized += "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _next_page_token(state: dict[str, object]) -> str | None:
    value = state.get("next_page_token")
    return value if isinstance(value, str) and value else None


def _page_size(value: int) -> int:
    return min(50, max(1, value))


def _window_size(value: int) -> int:
    return max(1, value)
