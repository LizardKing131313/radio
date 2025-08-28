from __future__ import annotations

import asyncio
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import ClassVar, Protocol

from structlog.typing import FilteringBoundLogger

from manager.runner.backoff import BackoffPolicy, BackoffState
from manager.runner.control import ControlMessage, ControlNode, ControlResult


Action = Callable[[], Awaitable[ControlResult]]


@dataclass(slots=True, kw_only=True)
class Runnable(ABC):
    """Интерфейс выполняемого процесса в раннере"""

    # имя для процесса
    name: str = field(init=False, repr=False)

    # время ожидания проверки готовности
    ready_timeout_sec: float = 20.0

    # время ожидания остановки процесса
    stop_timeout_sec: float = 15.0

    # политики перезапуска процесса
    @property
    def backoff_policy(self) -> BackoffPolicy:
        return BackoffPolicy()

    # состояние перезапуска процесса
    @property
    def backoff_state(self) -> BackoffState:
        return BackoffState(self.backoff_policy)

    # имя ноды, на которой запустили процесс
    node_id: ControlNode

    # интервал автоматического вызова check
    health_interval_sec: ClassVar[float] = 0.0

    # количество перезапусков при ошибке чека
    health_fail_threshold: int = 3

    def __post_init__(self) -> None:
        # установить имя процесса как имя ноды по умолчанию
        self.name = str(self.node_id)

    @abstractmethod
    async def start(
        self,
        log_event: FilteringBoundLogger,
        log_out: FilteringBoundLogger,
    ) -> NodeHandle | None: ...

    @abstractmethod
    async def mark_ready(
        self,
        ready_event: asyncio.Event,
        log_event: FilteringBoundLogger,
    ) -> ControlResult: ...

    @abstractmethod
    def get_ready_action(self) -> Action | None: ...

    @abstractmethod
    async def check(
        self,
        ready_event: asyncio.Event,
        log_event: FilteringBoundLogger,
    ) -> ControlResult: ...

    @abstractmethod
    async def receive(
        self,
        ready_event: asyncio.Event,
        message: ControlMessage,
        log_event: FilteringBoundLogger,
    ) -> ControlResult: ...

    @abstractmethod
    async def wait_or_shutdown(
        self, handle: NodeHandle, shutdown_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> int | None: ...

    @abstractmethod
    async def stop(
        self,
        handle: NodeHandle,
        reason: str,
        log_event: FilteringBoundLogger,
    ) -> None: ...


@dataclass(slots=True)
class Node:
    """Описание ноды процесса в раннере"""

    # имя ноды
    id: ControlNode
    # выполняемый процесс
    runnable: Runnable
    # список имен нод, от которых зависит нода
    parent: set[ControlNode] = field(default_factory=set)
    # флаг включения/отключения ноды из управления
    disabled: bool = False

    def __post_init__(self) -> None:
        if id is None:
            raise SystemExit("Node ID is required")
        self.runnable.node_id = self.id


@dataclass(slots=True)
class NodeHandle(Protocol):
    """Хэндл запущенной процесса ноды"""

    # время запуска процесса
    started_monotonic: float

    @property
    def pid(self) -> int | None: ...

    @property
    def uptime_seconds(self) -> float:
        """Получить текущее время работы"""

        return max(0.0, time.monotonic() - self.started_monotonic)

    @property
    def is_alive(self) -> bool:
        return True
