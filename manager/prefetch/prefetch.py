from __future__ import annotations

import asyncio
import contextlib
import os
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.prefetch.data import BlacklistState, ColdReady, Metrics
from manager.prefetch.utils import (
    SuppressTask,
    iso_after_minutes,
    iterate_files,
    now_iso,
    proc_exec,
    watch_url,
)
from manager.runner.control import (
    ControlAction,
    ControlBus,
    ControlMessage,
    ControlNode,
    ControlResult,
    Error,
    PayloadEnvelope,
    Success,
)
from manager.runner.service_runnable import ServiceRun, ServiceRunnable
from manager.track_queue.models import Track


class PrefetchService(ServiceRunnable):
    """
    Prefetch worker: downloads Opus to cold cache, promotes to hot,
    enforces LRU quotas, measures LUFS, and updates DB via bus.

    Complies with ServiceRunnable API. :contentReference[oaicite:1]{index=1}
    Uses Track model fields incl. v5 telemetry. :contentReference[oaicite:2]{index=2}
    """

    def __init__(
        self, node_id: ControlNode, control_bus: ControlBus, config: AppConfig | None = None
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()
        self._metrics = Metrics()
        self._blacklist = BlacklistState.load(self._config.paths.cache_blacklist)
        self._trigger = asyncio.Event()
        self._bus = control_bus
        self._pending: dict[str, asyncio.Future[list[Track]]] = {}

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def run(
            stop_event: asyncio.Event,
            ready_event_external: asyncio.Event,
            log: FilteringBoundLogger,
        ) -> int | None:
            await self._ensure_dirs(log)
            ready_event_external.set()
            self._trigger.set()

            while not stop_event.is_set():
                try:
                    await self._enforce_cold_quota(log)
                    tracks = await self._request_missing_tracks(
                        self._config.prefetch.batch_size, log
                    )
                    if tracks:
                        await self._process_tracks_parallel(tracks, stop_event, log)
                except Exception as exception:
                    log.error("prefetch loop error", name=self.name, error=str(exception))
                finally:
                    self._metrics.update_spaces(
                        self._config.paths.cache_cold,
                        self._config.paths.cache_hot,
                        self._config.prefetch.cold_quota_bytes,
                    )
                    await self._wait_interval_or_trigger(stop_event)

            with SuppressTask():
                self._blacklist.save(self._config.paths.cache_blacklist)
            return None

        return run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        try:
            await self._ensure_dirs(log_event)
            return Success("OK")
        except Exception as exception:
            return Error(f"check failed: {exception!s}")

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        log_event.info(event=f"received message {message!r}", node_id=self.node_id)
        if message.correlation_id is not None:
            log_event.info(
                event=f"received correlation_id {message.correlation_id}", node_id=self.node_id
            )
            match message.action:
                case ControlAction.MISSING_AUDIO_RESPONSE | ControlAction.TRACK_BY_ID_RESPONSE:
                    log_event.info(
                        event="action accepted", action=str(message.action), node_id=self.node_id
                    )
                    future = self._pending.pop(str(message.correlation_id), None)
                    if future and not future.done():
                        log_event.info(
                            event="future ready",
                            correlation_id=message.correlation_id,
                            node_id=self.node_id,
                        )
                        items = message.payload.data or []
                        tracks: list[Track] = []
                        for track in items:
                            try:
                                tracks.append(Track(**track))
                            except Exception:
                                tracks.append(Track.from_row(track))
                        future.set_result(tracks)
                        log_event.info(event="tracks received", tracks=tracks, node_id=self.node_id)
                        return Success("accepted")
                    log_event.warning(
                        event="future not found",
                        node_id=self.node_id,
                        correlation_id=message.correlation_id,
                    )
                case _:
                    return Error("unknown action")

        match message.action:
            case ControlAction.TRIGGER:
                self._trigger.set()
                return Success("triggered")
            case ControlAction.LOAD_HOT:
                match await self._schedule_track(message, log_event):
                    case Error() as error:
                        return error
                    case Success() as ok:
                        return ok
                    case ColdReady(youtube_id=youtube_id, path=cold):
                        await self._ensure_hot_link(cold, log_event)
                        await self._update_cache_hot(youtube_id, log_event)
                        return Success("hot-ready")

            case ControlAction.RECALC_LUFS:
                match await self._schedule_track(message, log_event):
                    case Error() as error:
                        return error
                    case Success() as ok:
                        return ok
                    case ColdReady(youtube_id=youtube_id, path=cold):
                        lufs = await self._measure_lufs(cold, log_event)
                        await self._bus.send(
                            ControlMessage(
                                node=ControlNode.DB,
                                action=ControlAction.UPDATE_TRACK_AUDIO,
                                payload=PayloadEnvelope(
                                    type="dict",
                                    data={
                                        "youtube_id": youtube_id,
                                        "loudness_lufs": float(lufs) if lufs is not None else None,
                                    },
                                ),
                            )
                        )
                        return Success(f"youtube_id: {youtube_id}, loudness_lufs: {lufs}")
            case ControlAction.STATS:
                return Success(str(self._metrics.as_dict()))
            case ControlAction.BLACKLIST_CLEAR:
                self._blacklist.clear()
                return Success("blacklist cleared")
            case ControlAction.BLACKLIST_REMOVE:
                youtube_id = message.payload.data.get("youtube_id")
                if not youtube_id:
                    return Error("youtube_id required")
                self._blacklist.remove(str(youtube_id))
                return Success(f"removed {youtube_id}")
            case _:
                return Error("unknown action")

    async def _schedule_track(
        self, message: ControlMessage, log: FilteringBoundLogger
    ) -> ColdReady | ControlResult:
        youtube_id = message.payload.data.get("youtube_id")
        track_id = message.payload.data.get("id")
        if not (youtube_id or track_id):
            return Error("id or youtube_id required")
        if not youtube_id and track_id:
            track_request = await self._request_track_by_id(int(track_id), log)
            youtube_id = track_request.youtube_id if track_request else None
        if not youtube_id:
            return Error("track not found")
        cold = self._config.paths.cache_cold / f"{youtube_id}.opus"
        if not cold.exists():
            self._trigger.set()
            return Success("scheduled")
        return ColdReady(youtube_id, cold)

    async def _process_tracks_parallel(
        self, tracks: list[Track], stop_event: asyncio.Event, log: FilteringBoundLogger
    ) -> None:
        semaphore = asyncio.Semaphore(max(1, self._config.prefetch.concurrent_downloads))

        async def worker(track: Track) -> None:
            async with semaphore:
                if stop_event.is_set():
                    return
                if self._blacklist.skip(track.youtube_id):
                    return

                cold_path = self._config.paths.cache_cold / f"{track.youtube_id}.opus"
                try:
                    if cold_path.exists():
                        self._metrics.hit()
                        await self._ensure_hot_link(cold_path, log)
                        await self._update_track_cached(track, cold_path)
                        self._blacklist.reset(track.youtube_id)
                        return

                    ok = await self._download_opus(track, cold_path, log)
                    if ok and cold_path.exists():
                        self._metrics.miss()
                        lufs = await self._measure_lufs(cold_path, log)
                        await self._ensure_hot_link(cold_path, log)
                        await self._update_track_downloaded(track, cold_path, lufs)
                        self._blacklist.reset(track.youtube_id)
                    else:
                        self._metrics.error()
                        self._blacklist.fail(track.youtube_id)
                        await self._bump_fail_count(track)
                except Exception as exception:
                    log.error(
                        "worker error",
                        id=track.id,
                        youtube_id=track.youtube_id,
                        error=str(exception),
                    )
                    self._metrics.error()
                    self._blacklist.fail(track.youtube_id)
                    await self._bump_fail_count(track)

        await asyncio.gather(*(worker(track) for track in tracks))

    async def _ensure_dirs(self, log: FilteringBoundLogger) -> None:
        self._config.paths.cache_cold.mkdir(parents=True, exist_ok=True)
        self._config.paths.cache_hot.mkdir(parents=True, exist_ok=True)
        self._config.paths.cache_blacklist.parent.mkdir(parents=True, exist_ok=True)
        log.info("prefetch dirs ready", name=self.name)

    async def _request_missing_tracks(self, limit: int, log: FilteringBoundLogger) -> list[Track]:
        correlation_id = uuid4()
        future: asyncio.Future[list[Track]] = asyncio.get_event_loop().create_future()
        self._pending[str(correlation_id)] = future
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.MISSING_AUDIO,
                payload=PayloadEnvelope(type="dict", data={"limit": int(limit)}),
                correlation_id=correlation_id,
            )
        )
        try:
            return await asyncio.wait_for(future, timeout=30.0)
        except asyncio.TimeoutError:  # noqa: UP041
            future = self._pending.pop(str(correlation_id), None)
            if future and not future.done():
                future.cancel()
            log.warning("db reply timeout MISSING_AUDIO", name=self.name)
            return []

    async def _request_track_by_id(self, track_id: int, log: FilteringBoundLogger) -> Track | None:
        correlation_id = uuid4()
        future: asyncio.Future[list[Track]] = asyncio.get_event_loop().create_future()
        self._pending[str(correlation_id)] = future
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.TRACK_BY_ID,
                payload=PayloadEnvelope(type="dict", data={"id": int(track_id)}),
                correlation_id=correlation_id,
            )
        )
        try:
            res = await asyncio.wait_for(future, timeout=15.0)
            return res[0] if res else None
        except asyncio.TimeoutError:  # noqa: UP041
            future = self._pending.pop(str(correlation_id), None)
            if future and not future.done():
                future.cancel()
            log.warning("db reply timeout TRACK_BY_ID", name=self.name)
            return None

    async def _update_track_downloaded(
        self, track: Track, cold_path: Path, lufs: float | None
    ) -> None:
        payload: dict[str, Any] = {
            "id": track.id,
            "audio_path": str(cold_path),
            "loudness_lufs": float(lufs) if lufs is not None else None,
            "cache_state": "cold",
            "last_prefetch_at": now_iso(),
            "fail_count": 0,
        }
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.UPDATE_TRACK_AUDIO,
                payload=PayloadEnvelope(type="dict", data=payload),
            )
        )

    async def _update_track_cached(self, track: Track, cold_path: Path) -> None:
        payload: dict[str, Any] = {
            "id": track.id,
            "audio_path": str(cold_path),
            "cache_state": "cold",
            "last_prefetch_at": now_iso(),
        }
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.UPDATE_TRACK_CACHED,
                payload=PayloadEnvelope(type="dict", data=payload),
            )
        )

    async def _update_cache_hot(self, youtube_id: str, _log: FilteringBoundLogger) -> None:
        payload: dict[str, Any] = {
            "youtube_id": youtube_id,
            "cache_state": "hot",
            "cache_hot_until": iso_after_minutes(self._config.prefetch.hot_ttl_minutes),
            "last_prefetch_at": now_iso(),
        }
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.UPDATE_TRACK_CACHE_STATE,
                payload=PayloadEnvelope(type="dict", data=payload),
            )
        )

    async def _bump_fail_count(self, track: Track) -> None:
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.TRACK_INCREMENT_FAIL_COUNT,
                payload=PayloadEnvelope(type="dict", data={"id": track.id}),
            )
        )

    async def _download_opus(self, track: Track, out_path: Path, log: FilteringBoundLogger) -> bool:
        url = track.url or watch_url(track.youtube_id)
        out_tmpl = str(out_path.with_name("%(id)s.%(ext)s"))
        args = [
            "yt-dlp",
            url,
            "--no-playlist",
            "--extract-audio",
            "--audio-format",
            "opus",
            "--audio-quality",
            "0",
            "--add-metadata",
            "--write-info-json",
            "--parse-metadata",
            "title:%(title)s",
            "--parse-metadata",
            "artist:%(uploader)s",
            "--output",
            out_tmpl,
            "--no-part",
            "--no-overwrites",
            "--quiet",
        ]
        if self._config.paths.cookies:
            args += ["--cookies", str(self._config.paths.cookies)]

        code, _out, error = await proc_exec(
            *args, timeout=self._config.prefetch.download_timeout_sec
        )
        if code != 0:
            log.warning("yt-dlp failed", name=self.name, code=code, err=(error or "").strip())
            return False

        expected = out_path.with_name(f"{track.youtube_id}.opus")
        if expected != out_path:
            with SuppressTask():
                if out_path.exists():
                    out_path.unlink()
            if expected.exists():
                expected.rename(out_path)
        return out_path.exists()

    async def _measure_lufs(self, path: Path, log: FilteringBoundLogger) -> float | None:
        args = [
            "ffmpeg",
            "-nostats",
            "-hide_banner",
            "-i",
            str(path),
            "-filter_complex",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ]
        code, _out, error = await proc_exec(*args, timeout=60)
        if code != 0:
            log.warning("lufs measure failed", name=self.name, code=code)
            return None
        match = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", error)
        try:
            return float(match.group(1)) if match else None
        except Exception:
            return None

    async def _ensure_hot_link(self, cold_path: Path, log: FilteringBoundLogger) -> Path:
        hot_dir: Path = self._config.paths.cache_hot
        hot_dir.mkdir(parents=True, exist_ok=True)

        hot_path: Path = hot_dir / cold_path.name
        if hot_path.exists():
            os.utime(hot_path, None)
            await self._enforce_hot_count(log)
            return hot_path

        tmp_path: Path = hot_path.with_suffix(hot_path.suffix + ".temp_copy")
        try:
            if tmp_path.exists():
                with contextlib.suppress(Exception):
                    tmp_path.unlink()

            shutil.copy2(cold_path, tmp_path)
            os.replace(tmp_path, hot_path)
            os.utime(hot_path, None)

            log.info("hot_copied", src=str(cold_path), dst=str(hot_path))
            await self._enforce_hot_count(log)
            return hot_path
        except Exception as exc:
            with contextlib.suppress(Exception):
                if tmp_path.exists():
                    tmp_path.unlink()
            log.warning("hot_copy_failed", err=str(exc), src=str(cold_path), dst=str(hot_path))
            raise

    async def _enforce_cold_quota(self, _log: FilteringBoundLogger) -> None:
        files: list[tuple[Path, float, int]] = []
        total = 0
        for path in iterate_files(self._config.paths.cache_cold):
            try:
                stat = path.stat()
                files.append((path, stat.st_mtime, stat.st_size))
                total += stat.st_size
            except Exception:
                continue
        if total <= self._config.prefetch.cold_quota_bytes:
            return
        files.sort(key=lambda x: x[1])
        index = 0
        while total > self._config.prefetch.cold_quota_bytes and index < len(files):
            path, _, size = files[index]
            with SuppressTask():
                path.unlink()
            total -= size
            index += 1

    async def _enforce_hot_count(self, _log: FilteringBoundLogger) -> None:
        files: list[tuple[Path, float]] = []
        for path in iterate_files(self._config.paths.cache_hot):
            try:
                stat = path.stat()
                files.append((path, stat.st_mtime))
            except Exception:
                continue
        if len(files) <= self._config.prefetch.hot_max_items:
            return
        files.sort(key=lambda file: file[1])
        need_remove = len(files) - self._config.prefetch.hot_max_items
        for i in range(need_remove):
            path, _ = files[i]
            with SuppressTask():
                path.unlink()

    async def _wait_interval_or_trigger(self, stop_event: asyncio.Event) -> None:
        sleeper = asyncio.create_task(asyncio.sleep(self._config.prefetch.interval_sec))
        trigger = asyncio.create_task(self._trigger.wait())
        stopper = asyncio.create_task(stop_event.wait())
        pending = None
        try:
            _, pending = await asyncio.wait(
                {sleeper, trigger, stopper}, return_when=asyncio.FIRST_COMPLETED
            )
        finally:
            for task in pending:
                task.cancel()
                with SuppressTask():
                    await task
            self._trigger.clear()
