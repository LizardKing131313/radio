from __future__ import annotations

import asyncio

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.runner.control import (
    ControlAction,
    ControlBus,
    ControlMessage,
    ControlNode,
    ControlResult,
    Error,
    Success,
)
from manager.runner.service_runnable import ServiceRun, ServiceRunnable
from manager.track_queue.db import Database
from manager.track_queue.repo import TracksRepo


class RepoService(ServiceRunnable):
    def __init__(
        self, node_id: ControlNode, control_bus: ControlBus, config: AppConfig | None = None
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._bus = control_bus
        self._config = config or get_settings()
        self._db: Database | None = None
        self._tracks: TracksRepo | None = None
        self._stop_event = None
        self._ready_event_external = None

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def _run(
            stop_event: asyncio.Event, ready_flag: asyncio.Event, log: FilteringBoundLogger
        ) -> int | None:
            self._ensure_repos()
            ready_flag.set()
            log.info("db loop started", name=self.name)
            try:
                await stop_event.wait()
                log.info("db loop stopping", name=self.name, reason="stop_event set")
            except Exception as exception:
                log.error("db loop exception", name=self.name, error=repr(exception))
                return 1
            return 0

        return _run

    def _ensure_repos(self) -> None:
        if self._db is None:
            self._db = Database()
            self._db.ensure_schema()
        if self._tracks is None:
            self._tracks = TracksRepo(self._db)

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
        if not ready_event.is_set():
            return Error("service not ready")
        try:
            match message.action:
                case ControlAction.INSERT_TRACKS:
                    upserted: int = 0
                    for track in message.payload:
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
                    return Success(f"ingested {upserted}")
                case ControlAction.MISSING_AUDIO:
                    limit = int(message.payload.get("limit", 10))
                    items = self._tracks.get_missing_audio(limit)
                    payload = [track.to_dict() for track in items]
                    await self._bus.send(
                        ControlMessage(
                            action=ControlAction.MISSING_AUDIO_RESPONSE,
                            node=ControlNode.FETCH,
                            payload=payload,
                            correlation_id=message.correlation_id,
                        )
                    )
                    return Success(f"sent {len(payload)}")
                case ControlAction.TRACK_BY_ID:
                    track_id = int(message.payload["id"])
                    track = self._tracks.get(track_id)
                    payload = [track.to_dict()] if track else []
                    await self._bus.send(
                        ControlMessage(
                            action=ControlAction.TRACK_BY_ID_RESPONSE,
                            node=ControlNode.FETCH,
                            payload=payload,
                            correlation_id=message.correlation_id,
                        )
                    )
                    return Success("sent 1" if track else "not found")
                case ControlAction.TRACK_INCREMENT_FAIL_COUNT:
                    self._tracks.increment_fail_count(track_id=int(message.payload["id"]))
                    return Success("updated")
                case ControlAction.UPDATE_TRACK_AUDIO:
                    self._tracks.update_track_audio(
                        track_id=int(message.payload["id"]),
                        audio_path=str(message.payload["audio_path"]),
                        loudness_lufs=(
                            float(message.payload["loudness_lufs"])
                            if message.payload.get("loudness_lufs") is not None
                            else None
                        ),
                    )
                    return Success("updated")
                case ControlAction.UPDATE_TRACK_CACHED:
                    self._tracks.update_track_cached(
                        track_id=int(message.payload["id"]),
                        cache_state=str(message.payload["cache_state"]),
                    )
                    return Success("updated")
                case ControlAction.UPDATE_TRACK_CACHE_STATE:
                    self._tracks.update_cache_state(
                        track_id=int(message.payload["id"]),
                        cache_state=str(message.payload["cache_state"]),
                        cache_hot_until=message.payload.get("cache_hot_until"),
                        last_prefetch_at=str(message.payload["last_prefetch_at"]),
                    )
                    return Success("updated")
                case _:
                    return Error(f"unknown action {message.action}")
        except Exception as exception:
            return Error(f"db request failed: {exception}")
