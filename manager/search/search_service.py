from __future__ import annotations

# YouTube search node (autostart, cookies REQUIRED, crawl-all then incremental) + 429 backoff.
# - No external files or state snapshots.
# - Node starts searching immediately.
# - Control: receive("stop") pauses, receive("start") resumes, receive("status") shows state,
#            receive("reindex") restarts full crawl, receive("lru.clear") clears local LRU.
# - Query: title (case-insensitive substring match).
# - Filters: duration 60..600 sec, category "Music" OR has track/artist, not live, not playlists.
# - Cookies: REQUIRED via cookies.txt (yt-dlp cookiefile).
# - LRU: remembers last N youtube_ids within process to avoid reprocessing across ticks.
# - Batch publish: one or several batches per tick through `_publish_discovered_batch(...)`
# (no-op by default).
# - 429 handling: exponential backoff with jitter when rate-limited.
# - Runtime strings/logs must be EN only.
import asyncio
import contextlib
import random
from datetime import UTC, datetime, timedelta

from structlog.typing import FilteringBoundLogger
from yt_dlp.utils import DownloadError

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
from manager.search.search_helpers import check_cookies, search_title_window
from manager.search.search_lru import LRUSet
from manager.track_queue.models import TrackDict


class SearchService(ServiceRunnable):
    """
    YouTube search node with:
      - AUTOSTART (search runs immediately),
      - REQUIRED cookies.txt,
      - full crawl (windows) on first run, then incremental (top window),
      - exponential backoff on HTTP 429.
    Publishes newly discovered tracks in BATCHES via
    `_publish_discovered_batch` hook (override in your project).
    """

    def __init__(
        self, node_id: ControlNode, control_bus: ControlBus, config: AppConfig | None = None
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()
        self._control_bus = control_bus

        # Lifecycle
        self._running = True  # AUTOSTART
        self._wakeup = asyncio.Event()
        self._stop_event: asyncio.Event | None = None
        self._ready_event_external: asyncio.Event | None = None

        # Modes and cursors (no external persistence by design)
        self._mode: str = "crawl"  # "crawl" | "incremental"
        self._cursor_start: int = 1  # 1-based

        # Status (for check/status)
        self._last_results: list[TrackDict] = []
        self._last_count_total: int = 0
        self._last_count_new: int = 0
        self._last_run_at: datetime | None = None
        self._last_error: str | None = None

        # Local de-dup across ticks (in-process only)
        self._seen_ids = LRUSet(capacity=self._config.search.lru_capacity)

        # 429 backoff state
        self._backoff_until: datetime | None = None
        self._backoff_attempts: int = 0

    # --------------------- Runner hooks ---------------------

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def _run(
            stop_event: asyncio.Event,
            ready_event_external: asyncio.Event,
            log_out: FilteringBoundLogger,
        ) -> int | None:
            self._stop_event = stop_event
            self._ready_event_external = ready_event_external

            ready_event_external.set()
            log_out.info(
                "service loop started",
                autostart=self._running,
                title=self._config.search.title,
                cookies=self._config.paths.cookies,
                mode=self._mode,
                window=self._config.search.window_size,
                max_windows_per_tick=self._config.search.max_windows_per_tick,
            )

            try:
                while not stop_event.is_set():
                    if not self._running:
                        self._wakeup.clear()
                        # ждём пробуждение, но не вечно
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(self._wakeup.wait(), timeout=0.5)
                        continue  # один continue достаточно

                    await self._do_search_once(log_out)

                    self._wakeup.clear()
                    with contextlib.suppress(asyncio.TimeoutError):
                        await asyncio.wait_for(self._wakeup.wait(), timeout=0)
            except Exception as e:
                log_out.error("Service loop failed", error=str(e))
            finally:
                log_out.info("Service loop stopped")

            return 0

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        if (
            self._ready_event_external is None
            or not self._ready_event_external.is_set()
            or not ready_event.is_set()
        ):
            log_event.warning("health not ready")
            return Error("not ready")

        cookies_ok, cookies_err = check_cookies(str(self._config.paths.cookies))
        if not cookies_ok:
            msg = f"cookies error: {cookies_err}"
            log_event.warning("health cookies failed", error=cookies_err)
            return Error(msg)

        state = "running" if self._running else "idle"
        extra = (
            f"mode={self._mode}, cursor={self._cursor_start}, "
            f"last_total={self._last_count_total}, last_new={self._last_count_new}, "
            f"lru_size={len(self._seen_ids)}"
        )
        if self._backoff_until and datetime.now(UTC) < self._backoff_until:
            extra += f", backoff_until={self._backoff_until.isoformat(timespec='seconds')}"
        if self._last_error:
            extra += f", error='{self._last_error}'"
        return Success(f"OK ({state}; {extra})")

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        match message.action:
            case ControlAction.START:
                if self._running:
                    return Success("already running")
                self._running = True
                self._wakeup.set()
                log_event.info("search started", title=self._config.search.title)
                return Success("started")
            case ControlAction.STATUS:
                state = "running" if self._running else "idle"
                when = (
                    self._last_run_at.isoformat(timespec="seconds")
                    if self._last_run_at
                    else "never"
                )
                extra = ""
                if self._backoff_until and datetime.now(UTC) < self._backoff_until:
                    extra = f", backoff_until={self._backoff_until.isoformat(timespec='seconds')}"
                return Success(
                    f"status {state}, mode={self._mode}, cursor={self._cursor_start}, "
                    f"window={self._config.search.window_size}, last_total={self._last_count_total}, "  # noqa: E501
                    f"last_new={self._last_count_new}, last_run_at={when}{extra}"
                )
            case ControlAction.REINDEX:
                self._mode = "crawl"
                self._cursor_start = 1
                self._wakeup.set()
                log_event.info("reindex requested: switched to crawl from start")
                return Success("reindex started (mode=crawl)")
            case ControlAction.CLEAR_LRU:
                self._seen_ids = LRUSet(capacity=self._config.search.lru_capacity)
                return Success("lru cleared")
            case ControlAction.STOP:
                if not self._running:
                    return Success("already stopped")
                self._running = False
                self._wakeup.set()
                log_event.info("search stopped")
                return Success("stopped")
            case _:
                return Error("Unknown action")

    async def _do_search_once(self, log_out: FilteringBoundLogger) -> None:
        # Backoff gate (after 429)
        if self._backoff_until and datetime.now(UTC) < self._backoff_until:
            log_out.warning(
                "backoff active",
                until=self._backoff_until.isoformat(timespec="seconds"),
                attempts=self._backoff_attempts,
            )
            await asyncio.sleep(0)
            return

        cookies_ok, cookies_err = check_cookies(str(self._config.paths.cookies))
        if not cookies_ok:
            self._last_error = f"cookies error: {cookies_err}"
            log_out.error("search tick skipped (cookies invalid)", error=cookies_err)
            await asyncio.sleep(0)
            return

        try:
            total_raw = 0
            total_new = 0
            publish_buffer: list[TrackDict] = []

            if self._mode == "crawl":
                windows = 0
                while windows < max(1, self._config.search.max_windows_per_tick):
                    start = self._cursor_start
                    end = start + self._config.search.window_size - 1

                    batch = await asyncio.get_running_loop().run_in_executor(
                        None,
                        search_title_window,
                        self._config.search.title,
                        str(self._config.paths.cookies),
                        start,
                        end,
                    )
                    total_raw += len(batch)

                    for td in batch:
                        vid = td["youtube_id"]
                        if vid in self._seen_ids:
                            continue
                        self._seen_ids.add(vid)
                        publish_buffer.append(td)

                    total_new = len(publish_buffer)

                    self._cursor_start += self._config.search.window_size
                    windows += 1
                    if len(batch) < self._config.search.window_size:
                        self._mode = "incremental"
                        self._cursor_start = 1
                        break

            else:
                start, end = 1, self._config.search.window_size
                batch = await asyncio.get_running_loop().run_in_executor(
                    None,
                    search_title_window,
                    self._config.search.title,
                    str(self._config.paths.cookies),
                    start,
                    end,
                )
                total_raw = len(batch)

                for td in batch:
                    vid = td["youtube_id"]
                    if vid in self._seen_ids:
                        continue
                    self._seen_ids.add(vid)
                    publish_buffer.append(td)
                    if len(publish_buffer) >= max(1, self._config.search.early_stop_new):
                        break

                total_new = len(publish_buffer)

            # Publish once per tick in batches (100..500 suggested)
            if publish_buffer:
                await self._publish_in_batches(publish_buffer, suggested_batch=500)

            # Success → reset backoff
            self._backoff_attempts = 0
            self._backoff_until = None

            # Update status
            self._last_results = publish_buffer
            self._last_count_total = total_raw
            self._last_count_new = total_new
            self._last_run_at = datetime.now(UTC)
            self._last_error = None

            log_out.info(
                "search tick ok",
                mode=self._mode,
                cursor=self._cursor_start,
                window=self._config.search.window_size,
                total=total_raw,
                new=total_new,
                lru_size=len(self._seen_ids),
            )
        except DownloadError as e:
            msg = str(e)
            self._last_error = msg
            if "HTTP Error 429" in msg or "429" in msg:
                # Exponential backoff with jitter: 30s, 60s, 120s, ... up to 30min.
                self._backoff_attempts = min(self._backoff_attempts + 1, 10)
                base = 30  # seconds
                delay = base * (2 ** (self._backoff_attempts - 1))
                delay = min(delay, 30 * 60)
                jitter = delay * random.uniform(-0.2, 0.2)
                delay = max(15, int(delay + jitter))
                self._backoff_until = datetime.now(UTC) + timedelta(seconds=delay)
                log_out.warning(
                    "rate limited (429), activating backoff",
                    attempts=self._backoff_attempts,
                    sleep_seconds=delay,
                    until=self._backoff_until.isoformat(timespec="seconds"),
                )
            else:
                log_out.error("yt-dlp download error", error=msg)
        except Exception as e:
            self._last_error = str(e)
            log_out.error("search tick failed", error=str(e))

    # --------------------- Publish hooks ---------------------

    async def _publish_in_batches(
        self, tracks: list[TrackDict], *, suggested_batch: int = 500
    ) -> None:
        """
        Split and forward tracks by chunks. Override `_publish_discovered_batch` in a subclass
        to route chunks into your DB writer (or call repo.upsert_batch directly).
        """
        if not tracks:
            return
        size = max(1, min(suggested_batch, 1000))  # hard cap
        for i in range(0, len(tracks), size):
            chunk = tracks[i : i + size]
            await self._control_bus.send(
                ControlMessage(ControlAction.INSERT_TRACKS, ControlNode.DB, chunk)
            )
