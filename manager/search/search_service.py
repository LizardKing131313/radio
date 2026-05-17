from __future__ import annotations

import asyncio

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.search.search_helpers import YouTubeAPIError, search_title_window
from manager.search.telemetry import (
    estimate_window_quota_units,
    is_youtube_quota_error,
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
    while True:
        sleep_sec = _next_sleep_sec(cfg)
        try:
            inserted = await search_once(cfg, tracks_repo, log)
            log.info("search tick ok", inserted=inserted)
        except YouTubeAPIError as exception:
            record_youtube_api_error(cfg.paths.youtube_telemetry_path, exception)
            sleep_sec = _next_sleep_sec(cfg, exception)
            log.warning("youtube api failed", error=str(exception), retry_after_sec=sleep_sec)
        except Exception as exception:
            log.warning("search tick failed", error=str(exception))
        await asyncio.sleep(sleep_sec)


async def search_once(config: AppConfig, tracks_repo: TracksRepo, log: FilteringBoundLogger) -> int:
    api_key = config.secrets.youtube_api_key.get_secret_value()
    inserted = 0

    for window_index in range(max(1, config.search.max_windows_per_tick)):
        # Сначала берем search.list, потом search_helpers добирает videos.list,
        # чтобы в БД попадали уже нормальные duration/title/channel.
        start = window_index * config.search.window_size + 1
        end = start + config.search.window_size - 1
        batch = await asyncio.get_running_loop().run_in_executor(
            None,
            search_title_window,
            config.search.title,
            api_key,
            start,
            end,
        )
        record_youtube_api_success(
            config.paths.youtube_telemetry_path,
            estimated_quota_units=estimate_window_quota_units(config.search.window_size),
            result_count=len(batch),
        )
        if not batch:
            break

        for track in batch:
            youtube_id = str(track["youtube_id"])
            tracks_repo.upsert(
                youtube_id=youtube_id,
                title=str(track["title"]),
                duration_sec=int(track["duration_sec"]),
                url=track.get("url"),
                channel=track.get("channel"),
                thumbnail_url=track.get("thumbnail_url"),
            )
            inserted += 1

    log.debug("search once done", inserted=inserted)
    return inserted


def _next_sleep_sec(config: AppConfig, error: BaseException | None = None) -> int:
    # При quotaExceeded нет смысла дергать YouTube каждую минуту: квота от этого
    # не восстановится, а логи и лимиты будут забиваться дальше.
    interval_sec = max(1, config.search.interval_sec)
    if error is not None and is_youtube_quota_error(error):
        return max(interval_sec, config.search.quota_backoff_sec)
    return interval_sec
