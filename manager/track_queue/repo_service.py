from __future__ import annotations

import asyncio
from collections.abc import Sequence

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.runner.control import (
    ControlAction,
    ControlMessage,
    ControlNode,
    ControlResult,
    Error,
    Success,
)
from manager.runner.node import Action
from manager.runner.service_runnable import ServiceRun, ServiceRunnable
from manager.track_queue.db import Database, DatabaseConfig
from manager.track_queue.repo import TracksRepo


class RepoService(ServiceRunnable):
    """
    Minimal ingest service:
    - run: set ready flag and wait for stop
    - check: Success("OK")
    - receive: accept 'tracks.batch' with payload of TrackDict list, upsert into DB
    """

    ready_timeout_sec: float
    stop_timeout_sec: float
    pragmas: Sequence[str] = (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA temp_store=MEMORY",
        "PRAGMA foreign_keys=ON",
    )

    def __init__(self, node_id: ControlNode, config: AppConfig | None = None) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()
        self._db: Database | None = None
        self._tracks: TracksRepo | None = None
        self._stop_event = None
        self._ready_event_external = None

    def _ensure_repos(self) -> None:
        if self._db is None:
            self._db = Database(
                DatabaseConfig(path=self._config.paths.data_base, pragmas=self.pragmas)
            )
            self._db.ensure_schema()
        if self._tracks is None:
            self._tracks = TracksRepo(self._db)

    def _get_ready_action(self) -> Action | None:
        pass

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def _run(
            stop_event: asyncio.Event, ready_flag: asyncio.Event, log: FilteringBoundLogger
        ) -> int | None:
            self._ensure_repos()
            ready_flag.set()
            log.info("ingest loop started", name=self.name)
            try:
                await stop_event.wait()
                log.info("ingest loop stopping", name=self.name, reason="stop_event set")
            except Exception as exc:
                log.error("ingest loop exception", name=self.name, error=repr(exc))
                return 1
            return 0

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        if ready_event.is_set():
            return Success("OK")
        return Error("not ready")

    async def receive(
        self,
        ready_event: asyncio.Event,
        message: ControlMessage,
        log_event: FilteringBoundLogger,
    ) -> ControlResult:
        """
        Accepts:
          - type/action/cmd == 'tracks.batch'
          - payload/data: Iterable[TrackDict]
        Each TrackDict must include at least:
          youtube_id: str, title: str, duration_sec: int, url: str
        Optional: channel, thumbnail_url, audio_path, loudness_lufs, is_active
        """
        if not ready_event.is_set():
            return Error("service not ready")

        if message.action != ControlAction.INSERT_TRACKS:
            return Error(f"unknown action {message.action}")

        # Попытка преобразовать payload к списку
        try:
            payload = list(message.payload)
        except TypeError:
            log_event.error("payload is not iterable", name=self.name, error=repr(message.payload))
            return Error("invalid payload type")

        try:
            self._ensure_repos()
            assert self._tracks is not None

            upserted: int = 0
            for track in payload:
                self._tracks.upsert(
                    youtube_id=track["youtube_id"],
                    title=track["title"],
                    duration_sec=int(track["duration_sec"]),
                    url=track["url"],
                    channel=track.get("channel"),
                    thumbnail_url=track.get("thumbnail_url"),
                    is_active=int(track.get("is_active", 1)),
                )
                upserted += 1

            log_event.info("tracks batch ingested", name=self.name, count=upserted)
            return Success(f"ingested {upserted}")
        except Exception as exc:
            log_event.error("ingest failed", name=self.name, error=repr(exc))
            return Error("ingest failed")
