from __future__ import annotations

import asyncio
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
    iter_files,
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
    Success,
)
from manager.runner.service_runnable import ServiceRun, ServiceRunnable
from manager.track_queue.models import Track


# Notes:
# - DB I/O is done via ControlBus messages only.
# - All paths/limits/TTLs come from PrefetchConfig (no hardcoded dirs).
# - User-facing strings are English-only.


class PrefetchService(ServiceRunnable):
    """
    Prefetch worker: downloads Opus to cold cache, promotes to hot,
    enforces LRU quotas, measures LUFS, and updates DB via bus.

    Complies with ServiceRunnable API. :contentReference[oaicite:1]{index=1}
    Uses Track model fields incl. v5 telemetry. :contentReference[oaicite:2]{index=2}
    """

    def __init__(
        self, node_id: ControlNode, bus: ControlBus, config: AppConfig | None = None
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()
        self._metrics = Metrics()
        self._blacklist = BlacklistState.load(self._config.paths.cache_blacklist)
        self._trigger = asyncio.Event()
        self._bus = bus
        self._pending: dict[str, asyncio.Future[list[Track]]] = {}

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def run(
            stop_ev: asyncio.Event, ready_ev_external: asyncio.Event, log: FilteringBoundLogger
        ) -> int | None:
            await self._ensure_dirs(log)
            ready_ev_external.set()
            self._trigger.set()

            while not stop_ev.is_set():
                try:
                    await self._enforce_cold_quota(log)
                    tracks = await self._request_missing_tracks(
                        self._config.prefetch.batch_size, log
                    )
                    if tracks:
                        await self._process_tracks_parallel(tracks, stop_ev, log)
                except Exception as e:
                    log.error("prefetch loop error", name=self.name, err=str(e))
                finally:
                    self._metrics.update_spaces(
                        self._config.paths.cache_cold,
                        self._config.paths.cache_hot,
                        self._config.prefetch.cold_quota_bytes,
                    )
                    await self._wait_interval_or_trigger(stop_ev)

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
        except Exception as e:
            return Error(f"check failed: {e!s}")

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        if message.correlation_id is not None:
            match message.action:
                case ControlAction.MISSING_AUDIO_RESPONSE, ControlAction.TRACK_BY_ID_RESPONSE:
                    fut = self._pending.pop(str(message.correlation_id), None)
                    if fut and not fut.done():
                        items = message.payload.get("tracks", []) or []
                        tracks: list[Track] = []
                        for t in items:
                            try:
                                tracks.append(Track(**t))
                            except Exception:
                                tracks.append(Track.from_row(t))
                        fut.set_result(tracks)
                        return Success("accepted")
                case _:
                    return Error("unknown action")

        match message.action:
            case ControlAction.TRIGGER:
                self._trigger.set()
                return Success("triggered")
            case ControlAction.LOAD_HOT:
                match await self._schedule_track(message, log_event):
                    case Error() as err:
                        return err
                    case Success() as ok:  # scheduled
                        return ok
                    case ColdReady(youtube_id=yid, path=cold):
                        await self._ensure_hot_link(cold, log_event)
                        await self._update_cache_hot(yid, log_event)
                        return Success("hot-ready")

            case ControlAction.RECALC_LUFS:
                match await self._schedule_track(message, log_event):
                    case Error() as err:
                        return err
                    case Success() as ok:  # scheduled
                        return ok
                    case ColdReady(youtube_id=yid, path=cold):
                        lufs = await self._measure_lufs(cold, log_event)
                        await self._bus.send(
                            ControlMessage(
                                node=ControlNode.DB,
                                action=ControlAction.UPDATE_TRACK_AUDIO,
                                payload={
                                    "youtube_id": yid,
                                    "loudness_lufs": float(lufs) if lufs is not None else None,
                                },
                            )
                        )
                        return Success(f"youtube_id: {yid}, loudness_lufs: {lufs}")
            case ControlAction.STATS:
                return Success(str(self._metrics.as_dict()))
            case ControlAction.BLACKLIST_CLEAR:
                self._blacklist.clear()
                return Success("blacklist cleared")
            case ControlAction.BLACKLIST_REMOVE:
                yid = message.payload.get("youtube_id")
                if not yid:
                    return Error("youtube_id required")
                self._blacklist.remove(str(yid))
                return Success(f"removed {yid}")
            case _:
                return Error("unknown action")

    async def _schedule_track(
        self, message: ControlMessage, log: FilteringBoundLogger
    ) -> ColdReady | ControlResult:
        yid = message.payload.get("youtube_id")
        track_id = message.payload.get("id")
        if not (yid or track_id):
            return Error("id or youtube_id required")
        if not yid and track_id:
            tr = await self._request_track_by_id(int(track_id), log)
            yid = tr.youtube_id if tr else None
        if not yid:
            return Error("track not found")
        cold = self._config.paths.cache_cold / f"{yid}.opus"
        if not cold.exists():
            self._trigger.set()
            return Success("scheduled")
        return ColdReady(yid, cold)

    async def _process_tracks_parallel(
        self, tracks: list[Track], stop_ev: asyncio.Event, log: FilteringBoundLogger
    ) -> None:
        sem = asyncio.Semaphore(max(1, self._config.prefetch.concurrent_downloads))

        async def worker(tr: Track) -> None:
            async with sem:
                if stop_ev.is_set():
                    return
                if self._blacklist.skip(tr.youtube_id):
                    return

                cold_path = self._config.paths.cache_cold / f"{tr.youtube_id}.opus"
                try:
                    if cold_path.exists():
                        self._metrics.hit()
                        await self._ensure_hot_link(cold_path, log)
                        await self._update_track_cached(tr, cold_path)
                        self._blacklist.reset(tr.youtube_id)
                        return

                    ok = await self._download_opus(tr, cold_path, log)
                    if ok and cold_path.exists():
                        self._metrics.miss()
                        lufs = await self._measure_lufs(cold_path, log)
                        await self._ensure_hot_link(cold_path, log)
                        await self._update_track_downloaded(tr, cold_path, lufs)
                        self._blacklist.reset(tr.youtube_id)
                    else:
                        self._metrics.error()
                        self._blacklist.fail(tr.youtube_id)
                        await self._bump_fail_count(tr)
                except Exception as e:
                    log.error("worker error", id=tr.id, yid=tr.youtube_id, err=str(e))
                    self._metrics.error()
                    self._blacklist.fail(tr.youtube_id)
                    await self._bump_fail_count(tr)

        await asyncio.gather(*(worker(t) for t in tracks))

    async def _ensure_dirs(self, log: FilteringBoundLogger) -> None:
        self._config.paths.cache_cold.mkdir(parents=True, exist_ok=True)
        self._config.paths.cache_hot.mkdir(parents=True, exist_ok=True)
        self._config.paths.cache_blacklist.parent.mkdir(parents=True, exist_ok=True)
        log.info("prefetch dirs ready", name=self.name)

    async def _request_missing_tracks(self, limit: int, log: FilteringBoundLogger) -> list[Track]:
        correlation_id = uuid4()
        fut: asyncio.Future[list[Track]] = asyncio.get_event_loop().create_future()
        self._pending[str(correlation_id)] = fut
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.MISSING_AUDIO,
                payload={"limit": int(limit)},
                correlation_id=correlation_id,
            )
        )
        try:
            return await asyncio.wait_for(fut, timeout=10.0)
        except asyncio.TimeoutError:  # noqa: UP041
            await self._pending.pop(str(correlation_id), None)
            log.warning("db reply timeout MISSING_AUDIO", name=self.name)
            return []

    async def _request_track_by_id(self, track_id: int, log: FilteringBoundLogger) -> Track | None:
        correlation_id = uuid4()
        fut: asyncio.Future[list[Track]] = asyncio.get_event_loop().create_future()
        self._pending[str(correlation_id)] = fut
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.TRACK_BY_ID,
                payload={"id": int(track_id)},
                correlation_id=correlation_id,
            )
        )
        try:
            res = await asyncio.wait_for(fut, timeout=5.0)
            return res[0] if res else None
        except asyncio.TimeoutError:  # noqa: UP041
            await self._pending.pop(str(correlation_id), None)
            log.warning("db reply timeout TRACK_BY_ID", name=self.name)
            return None

    async def _update_track_downloaded(self, t: Track, cold_path: Path, lufs: float | None) -> None:
        payload: dict[str, Any] = {
            "id": t.id,
            "audio_path": str(cold_path),
            "loudness_lufs": float(lufs) if lufs is not None else None,
            "cache_state": "cold",
            "last_prefetch_at": now_iso(),
            "fail_count": 0,
        }
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB, action=ControlAction.UPDATE_TRACK_AUDIO, payload=payload
            )
        )

    async def _update_track_cached(self, t: Track, cold_path: Path) -> None:
        payload: dict[str, Any] = {
            "id": t.id,
            "audio_path": str(cold_path),
            "cache_state": "cold",
            "last_prefetch_at": now_iso(),
        }
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB, action=ControlAction.UPDATE_TRACK_CACHED, payload=payload
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
                node=ControlNode.DB, action=ControlAction.UPDATE_TRACK_CACHE_STATE, payload=payload
            )
        )

    async def _bump_fail_count(self, t: Track) -> None:
        await self._bus.send(
            ControlMessage(
                node=ControlNode.DB,
                action=ControlAction.TRACK_INCREMENT_FAIL_COUNT,
                payload={"id": t.id, "fail_count_inc": 1, "last_prefetch_at": now_iso()},
            )
        )

    async def _download_opus(self, t: Track, out_path: Path, log: FilteringBoundLogger) -> bool:
        url = t.url or watch_url(t.youtube_id)
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
            "--output",
            out_tmpl,
            "--no-part",
            "--no-overwrites",
            "--quiet",
        ]
        if self._config.paths.cookies:
            args += ["--cookies", str(self._config.paths.cookies)]

        code, _out, err = await proc_exec(*args, timeout=self._config.prefetch.download_timeout_sec)
        if code != 0:
            log.warning("yt-dlp failed", name=self.name, code=code, err=(err or "").strip())
            return False

        expected = out_path.with_name(f"{t.youtube_id}.opus")
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
        code, _out, err = await proc_exec(*args, timeout=60)
        if code != 0:
            log.warning("lufs measure failed", name=self.name, code=code)
            return None
        m = re.search(r"I:\s*(-?\d+(?:\.\d+)?)\s*LUFS", err)
        try:
            return float(m.group(1)) if m else None
        except Exception:
            return None

    async def _ensure_hot_link(self, cold_path: Path, log: FilteringBoundLogger) -> None:
        hot_path = self._config.paths.cache_hot / cold_path.name
        if hot_path.exists():
            with SuppressTask():
                os.utime(hot_path, None)
        else:
            with SuppressTask():
                hot_path.symlink_to(cold_path)
            if not hot_path.exists():
                with SuppressTask():
                    os.link(cold_path, hot_path)
            if not hot_path.exists():
                shutil.copy2(cold_path, hot_path)
        await self._enforce_hot_count(log)

    async def _enforce_cold_quota(self, _log: FilteringBoundLogger) -> None:
        files: list[tuple[Path, float, int]] = []
        total = 0
        for p in iter_files(self._config.paths.cache_cold):
            try:
                st = p.stat()
                files.append((p, st.st_mtime, st.st_size))
                total += st.st_size
            except Exception:
                continue
        if total <= self._config.prefetch.cold_quota_bytes:
            return
        files.sort(key=lambda x: x[1])
        idx = 0
        while total > self._config.prefetch.cold_quota_bytes and idx < len(files):
            p, _mt, sz = files[idx]
            with SuppressTask():
                p.unlink()
            total -= sz
            idx += 1

    async def _enforce_hot_count(self, _log: FilteringBoundLogger) -> None:
        files: list[tuple[Path, float]] = []
        for p in iter_files(self._config.paths.cache_hot):
            try:
                st = p.stat()
                files.append((p, st.st_mtime))
            except Exception:
                continue
        if len(files) <= self._config.prefetch.hot_max_items:
            return
        files.sort(key=lambda x: x[1])
        need_remove = len(files) - self._config.prefetch.hot_max_items
        for i in range(need_remove):
            p, _ = files[i]
            with SuppressTask():
                p.unlink()

    async def _wait_interval_or_trigger(self, stop_ev: asyncio.Event) -> None:
        sleeper = asyncio.create_task(asyncio.sleep(self._config.prefetch.interval_sec))
        trigger = asyncio.create_task(self._trigger.wait())
        stopper = asyncio.create_task(stop_ev.wait())
        _, pending = await asyncio.wait(
            {sleeper, trigger, stopper}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
            with SuppressTask():
                await t
        self._trigger.clear()
