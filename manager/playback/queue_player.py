from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.playback.telnet import LiquidsoapTelnetClient, LiquidsoapTelnetError
from manager.track_queue.db import Database
from manager.track_queue.models import QueueItem, Track
from manager.track_queue.repo import QueueRepo, TracksRepo


class QueueTelnetClient(Protocol):
    def push_request(self, uri: str) -> str: ...  # pragma: no cover

    def queue_requests(self) -> str: ...  # pragma: no cover

    def play_now_status(self) -> str: ...  # pragma: no cover


@dataclass(frozen=True)
class QueueMetadata:
    queue_id: int | None
    track_id: int | None
    queue_kind: str | None = None


class QueuePlayer:
    def __init__(
        self,
        config: AppConfig | None = None,
        database: Database | None = None,
        liquidsoap: QueueTelnetClient | None = None,
    ) -> None:
        self.config = config or get_settings()
        self.database = database or Database(app_config=self.config)
        self.queue = QueueRepo(self.database)
        self.tracks = TracksRepo(self.database)
        self.liquidsoap = liquidsoap or LiquidsoapTelnetClient()
        self.log = get_logger("queue-player")
        self._missing_playing_metadata_ticks = 0
        self._missing_queued_request_ticks = 0

    async def run_forever(self) -> None:  # pragma: no cover - бесконечный CLI-loop.
        self.database.ensure_schema()
        while True:
            try:
                self.tick()
            except Exception as exception:
                self.log.warning("queue player tick failed", error=str(exception))
            await asyncio.sleep(1)

    def close(self) -> None:
        self.database.close()

    def tick(self) -> None:
        metadata = read_queue_metadata(self.config.paths.nowplaying_path)
        self._finish_old_playing(metadata)
        self._mark_started(metadata)
        self._release_lost_queued(metadata)
        self._push_next_if_needed()
        self.queue.cleanup_done()

    def _finish_old_playing(self, metadata: QueueMetadata) -> None:
        current = self.queue.current_playing()
        if current is None:
            self._missing_playing_metadata_ticks = 0
            return
        queue_item, track = current
        if metadata.queue_id == queue_item.id or metadata.track_id == track.id:
            self._missing_playing_metadata_ticks = 0
            return
        if metadata.queue_id is None:
            self._missing_playing_metadata_ticks += 1
            if self._missing_playing_metadata_ticks < 3:
                return
        self._missing_playing_metadata_ticks = 0
        self.queue.mark_done(queue_item.id)
        self.log.info("queue item finished", queue_id=queue_item.id)

    def _mark_started(self, metadata: QueueMetadata) -> None:
        if metadata.queue_id is None:
            return
        active = self.queue.current_active()
        if active is None:
            return
        queue_item, track = active
        if queue_item.id != metadata.queue_id:
            return
        if queue_item.status == "queued":
            self.queue.mark_playing(queue_item.id)
            self.tracks.touch_play(track.id)
            self.log.info("queue item started", queue_id=queue_item.id, track_id=track.id)

    def _release_lost_queued(self, metadata: QueueMetadata) -> None:
        if metadata.queue_id is not None:
            self._missing_queued_request_ticks = 0
            return
        active = self.queue.current_active()
        if active is None:
            self._missing_queued_request_ticks = 0
            return
        queue_item, _track = active
        if queue_item.status != "queued":
            self._missing_queued_request_ticks = 0
            return
        if self.liquidsoap.queue_requests().strip() or self.liquidsoap.play_now_status().strip():
            self._missing_queued_request_ticks = 0
            return
        self._missing_queued_request_ticks += 1
        if self._missing_queued_request_ticks < 3:
            return
        self.queue.release_queued(queue_item.id)
        self._missing_queued_request_ticks = 0
        self.log.warning("queued item returned to pending because liquidsoap queue is empty")

    def _push_next_if_needed(self) -> None:
        if self.queue.current_queued() is not None:
            return
        reserved = self.queue.reserve_next()
        if reserved is None:
            return
        queue_item, track = reserved
        path = _audio_path(track)
        if path is None or not path.exists():
            error_detail = (
                "track has no audio_path" if path is None else f"audio file is missing: {path}"
            )
            self.queue.mark_failed(queue_item.id, error_detail)
            self.log.warning(
                "queue item failed because audio file is missing",
                queue_id=queue_item.id,
                track_id=track.id,
                error_detail=error_detail,
                audio_path=str(path) if path is not None else None,
            )
            return
        try:
            self.liquidsoap.push_request(_annotated_uri(queue_item, track, path))
        except LiquidsoapTelnetError:
            self.queue.release_queued(queue_item.id)
            raise
        self.log.info("queue item pushed to liquidsoap", queue_id=queue_item.id)


def read_queue_metadata(nowplaying_path: Path) -> QueueMetadata:
    # Liquidsoap пишет queue_id/track_id в nowplaying.txt.kv только для request.queue.
    values = _read_kv(nowplaying_path.with_name(nowplaying_path.name + ".kv"))
    return QueueMetadata(
        queue_id=_int_or_none(values.get("queue_id")),
        track_id=_int_or_none(values.get("track_id")),
        queue_kind=_str_or_none(values.get("queue_kind")),
    )


def _read_kv(path: Path) -> dict[str, str]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            values[key] = value
    return values


def _int_or_none(value: str | None) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _str_or_none(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    return value


def _audio_path(track: Track) -> Path | None:
    return Path(track.audio_path) if track.audio_path else None


def _annotated_uri(queue_item: QueueItem, track: Track, path: Path) -> str:
    # annotate добавляет метки, которые Liquidsoap потом пробрасывает в metadata.
    normalized = str(path).replace("\\", "/")
    return f'annotate:queue_id="{queue_item.id}",track_id="{track.id}":{normalized}'
