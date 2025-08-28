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
    ControlMessage,
    ControlNode,
    ControlResult,
    Error,
    Success,
)
from manager.runner.node import Action
from manager.runner.process_runnable import ProcessCommand, ProcessRunnable


class LiquidSoap(ProcessRunnable):

    health_interval_sec: ClassVar[float] = 5.0

    def __init__(self, node_id: ControlNode, config: AppConfig | None = None) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self.config = config or get_settings()
        self.telnet = Telnet()

    @cached_property
    def command(self) -> ProcessCommand:
        return ProcessCommand(
            exe="/usr/bin/liquidsoap",
            args=["-v", str(self.config.paths.data / "radio.liq")],
            cwd=str(self.config.paths.base),
            env={"LS_TELNET_PORT": str(self.config.liquidsoap.telnet_port)},
        )

    @cached_property
    def backoff_policy(self) -> BackoffPolicy:
        return BackoffPolicy(max_sec=self.config.liquidsoap.restart_timer_max_sec)

    def get_ready_action(self) -> Action | None:
        async def _run() -> ControlResult:
            loop = asyncio.get_running_loop()
            deadline = loop.time() + float(self.ready_timeout_sec)
            while loop.time() < deadline:
                res = await self.telnet.connect_only()
                if res.is_ok:
                    return Success("liquidsoap ready")
                await asyncio.sleep(0.1)
            return Error("liquidsoap did not respond in time")

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        # быстрый health: достаточно TCP-коннекта
        res = await self.telnet.connect_only()
        return Success("ok") if res.is_ok else res

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        match message.action:
            case ControlAction.SKIP:
                return await self.telnet.skip()
            case ControlAction.PUSH:
                return await self.telnet.push(message.payload)
            case ControlAction.POP:
                return await self.telnet.skip()
            case ControlAction.QUEUE:
                return await self.telnet.vars()
            case _:
                return Error("unknown action")
