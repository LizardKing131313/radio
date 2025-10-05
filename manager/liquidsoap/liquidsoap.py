from __future__ import annotations

import asyncio
from functools import cached_property
from typing import ClassVar

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.liquidsoap.telnet import Telnet
from manager.runner.backoff import BackoffPolicy
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
from manager.runner.node import Action
from manager.runner.process_runnable import ProcessCommand, ProcessRunnable


class LiquidSoap(ProcessRunnable):
    health_interval_sec: ClassVar[float] = 5.0

    def __init__(
        self, node_id: ControlNode, control_bus: ControlBus, config: AppConfig | None = None
    ) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()
        self._telnet = Telnet()
        self._bus = control_bus

    @cached_property
    def command(self) -> ProcessCommand:
        return ProcessCommand(
            exe="/usr/bin/liquidsoap",
            args=["-v", str(self._config.paths.data / "radio.liq")],
            cwd=str(self._config.paths.base),
            env={"LS_TELNET_PORT": str(self._config.liquidsoap.telnet_port)},
        )

    @cached_property
    def backoff_policy(self) -> BackoffPolicy:
        return BackoffPolicy(max_sec=self._config.liquidsoap.restart_timer_max_sec)

    def _get_ready_action(self) -> Action | None:
        async def _run() -> ControlResult:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + float(self.ready_timeout_sec)
            while loop.time() < deadline:
                res = await self._telnet.connect_only()
                if res.is_ok:
                    return Success("liquidsoap ready")
                await asyncio.sleep(0.1)
            return Error("liquidsoap did not respond in time")

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        # быстрый health: достаточно TCP-коннекта
        res = await self._telnet.connect_only()
        return Success("ok") if res.is_ok else res

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        match message.action:
            case ControlAction.SKIP:
                return await self._telnet.hot_skip()
            case ControlAction.PUSH:
                return await self._telnet.hot_uri(str(message.payload.data.get("hot_uri")))
            case ControlAction.POP:
                return await self._telnet.hot_next()
            case ControlAction.QUEUE:
                result = await self._telnet.rq_queue()
                queue = ""
                if result.is_ok:
                    queue = result.message
                await self._bus.send(
                    ControlMessage(
                        action=ControlAction.QUEUE_RESPONSE,
                        node=ControlNode.COORDINATOR,
                        payload=PayloadEnvelope(type="dict", data={"queue": queue}),
                    )
                )
                return result
            case _:
                return Error("unknown action")
