from __future__ import annotations

import asyncio
import contextlib
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from structlog.typing import FilteringBoundLogger

from manager.runner.control import ControlResult, Error, Success
from manager.runner.node import NodeHandle, Runnable


ServiceRun = Callable[
    [asyncio.Event, asyncio.Event, FilteringBoundLogger], Coroutine[Any, Any, int | None]
]


@dataclass(slots=True)
class ServiceHandle(NodeHandle):

    # время запуска процесса
    started_monotonic: float

    task: asyncio.Task[int | None]

    @property
    def pid(self) -> int | None:
        return None


@dataclass(slots=True)
class ServiceRunnable(Runnable, ABC):
    """Выполняемый сервис"""

    _stop_event: asyncio.Event
    _ready_event_external: asyncio.Event

    async def start(
        self, log_event: FilteringBoundLogger, log_out: FilteringBoundLogger
    ) -> NodeHandle | None:
        run = self.get_service_run()
        if run is None:
            log_event.error("service start error", name=self.name, error="No run method provided")
            return None

        self._stop_event = asyncio.Event()
        self._ready_event_external = asyncio.Event()

        run_task = run(self._stop_event, self._ready_event_external, log_out)
        task = asyncio.create_task(run_task, name=f"svc:{self.node_id}")

        self.backoff_state.register_start()

        log_event.info("service started", name=self.name)
        return ServiceHandle(started_monotonic=time.monotonic(), task=task)

    @abstractmethod
    def get_service_run(self) -> ServiceRun | None: ...

    async def mark_ready(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        try:
            await asyncio.wait_for(
                self._ready_event_external.wait(), timeout=self.ready_timeout_sec
            )
            ready_event.set()
            success_message = "service ready"
            log_event.info(success_message, name=self.name)
            return Success(success_message)
        except asyncio.TimeoutError:  # noqa: UP041
            error_message = "service ready timeout"
            log_event.warning(error_message, name=self.name, timeout_s=self.ready_timeout_sec)
            return Error(error_message)

    async def wait_or_shutdown(
        self, handle: NodeHandle, shutdown_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> int | None:
        """Wait until process exits or shutdown requested."""
        assert isinstance(handle, ServiceHandle)

        proc_wait = handle.task
        proc_wait.set_name("wait:svc_exit")
        shut_wait = asyncio.create_task(shutdown_event.wait(), name="wait:shutdown")

        done, pending = await asyncio.wait(
            {proc_wait, shut_wait}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        with contextlib.suppress(Exception):
            await self.stop(handle, reason="shutdown", log_event=log_event)
        return None

    async def stop(self, handle: NodeHandle, reason: str, log_event: FilteringBoundLogger) -> None:
        assert isinstance(handle, ServiceHandle)
        self._stop_event.set()
        try:
            await asyncio.wait_for(handle.task, timeout=self.stop_timeout_sec)
            log_event.info("service stopped", name=self.name, reason=reason)
        except asyncio.TimeoutError:  # noqa: UP041
            handle.task.cancel()
            with contextlib.suppress(Exception):
                await handle.task
            log_event.warning("service cancelled", name=self.name, reason=reason)
