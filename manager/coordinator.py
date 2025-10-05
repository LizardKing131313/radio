from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable
from pathlib import PurePosixPath
from urllib.parse import urlparse

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
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


_YOUTUBE_ID_REGEXP: re.Pattern[str] = re.compile(r"(?P<id>[A-Za-z0-9_-]{11})(?:\.[^/?#]+)?$")


class CoordinatorService(ServiceRunnable):
    def __init__(
        self,
        node_id: ControlNode,
        control_bus: ControlBus,
        config: AppConfig | None = None,
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._bus = control_bus
        self._config = config or get_settings()

        self._response_event: asyncio.Event | None = None
        self._last_queue_raw: str = ""

        self._interval_sec: int = self._config.coordinator.interval_sec
        self._hot_window_size: int = self._config.coordinator.hot_window_size

    # noinspection PyTypeHints
    def _get_service_run(self) -> ServiceRun | None:
        async def run(
            stop_event: asyncio.Event,
            ready_event_external: asyncio.Event,
            log: FilteringBoundLogger,
        ) -> int | None:
            ready_event_external.set()
            log.info(
                "coordinator started",
                interval_sec=self._interval_sec,
                hot_window_size=self._hot_window_size,
                node_id=self.node_id,
            )
            try:
                while not stop_event.is_set():
                    await self._tick_once(log)
                    sleep_task = asyncio.create_task(asyncio.sleep(self._interval_sec))
                    stop_task = asyncio.create_task(stop_event.wait())
                    done, _ = await asyncio.wait(
                        {sleep_task, stop_task},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    for task in done:
                        task.cancel()
            except Exception as exception:
                log.error("coordinator loop crashed", error=str(exception), node_id=self.node_id)
            finally:
                log.info("coordinator stopped", node_id=self.node_id)
            return None

        return run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        return Success("ok") if ready_event.is_set() else Error("not ready")

    async def receive(
        self,
        ready_event: asyncio.Event,
        message: ControlMessage,
        log_event: FilteringBoundLogger,
    ) -> ControlResult:
        if message.action == ControlAction.QUEUE_RESPONSE:
            try:
                log_event.info(
                    event="LS response", node_id=self.node_id, payload=message.payload.data
                )
                payload = message.payload.data if message.payload else {}
                queue_raw = str(payload.get("queue", "")).strip()
                self._last_queue_raw = queue_raw
                event = self._response_event
                if event is not None and not event.is_set():
                    event.set()
                return Success("queue received")
            except Exception as exception:
                return Error(f"failed to parse queue: {exception}")
        return Error("unknown action")

    async def _tick_once(self, log: FilteringBoundLogger) -> None:
        self._response_event = asyncio.Event()
        await self._bus.send(
            ControlMessage(action=ControlAction.QUEUE, node=ControlNode.LIQUID_SOAP)
        )

        try:
            await asyncio.wait_for(self._response_event.wait(), timeout=2.5)
        except TimeoutError:
            log.warning("ls queue response timeout", node_id=self.node_id)
            return
        finally:
            self._response_event = None

        uri_list = self._normalize_queue_lines(self._last_queue_raw)
        if not uri_list:
            log.warning("empty queue or unparsable", node_id=self.node_id)
            return

        ids = self._unique_keep_order(self._extract_youtube_id(uri) for uri in uri_list)
        if not ids:
            log.warning("no youtube ids parsed", items=len(uri_list), node_id=self.node_id)
            return

        target = ids[: max(1, self._hot_window_size)]
        for youtube_id in target:
            await self._bus.send(
                ControlMessage(
                    action=ControlAction.LOAD_HOT,
                    node=ControlNode.FETCH,
                    payload=PayloadEnvelope(type="dict", data={"youtube_id": youtube_id}),
                )
            )
        await self._bus.send(ControlMessage(action=ControlAction.TRIGGER, node=ControlNode.FETCH))

        log.info(
            event="prefetch nudged",
            requested=len(target),
            sample=", ".join(target[:5]),
            node_id=self.node_id,
        )

    @staticmethod
    def _normalize_queue_lines(raw: str) -> list[str]:
        if not raw:
            return []
        lines = [line.strip() for line in raw.splitlines() if line.strip()]
        if len(lines) == 1 and "," in lines[0]:
            parts = [part.strip() for part in lines[0].split(",")]
            lines = [part for part in parts if part]
        return lines

    @staticmethod
    def _extract_youtube_id(uri: str) -> str | None:
        try:
            parsed = urlparse(uri)
            path = parsed.path if parsed.scheme else uri
            name = PurePosixPath(path).name
            match = _YOUTUBE_ID_REGEXP.search(name)
            return match.group("id") if match else None
        except Exception:
            return None

    @staticmethod
    def _unique_keep_order(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out
