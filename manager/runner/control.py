from __future__ import annotations

from asyncio import Queue
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ControlNode(StrEnum):
    """Список всех нод под управлением раннера"""

    LIQUID_SOAP = "LIQUID_SOAP"
    FFMPEG = "FFMPEG"
    FETCH = "FETCH"
    NOW_PLAYING = "NOW_PLAYING"
    SEARCH = "SEARCH"
    API = "API"
    DB = "DB"
    COORDINATOR = "COORDINATOR"


class ControlAction(StrEnum):
    """Список всех управляющих команд"""

    # Runner
    STOP_ALL = "STOP_ALL"
    STOP_NODE = "STOP_NODE"

    # Common
    START = "START"
    STATUS = "STATUS"
    STOP = "STOP"

    # LiquidSoap
    SKIP = "SKIP"
    PUSH = "PUSH"
    POP = "POP"
    QUEUE = "QUEUE"
    QUEUE_RESPONSE = "QUEUE_RESPONSE"

    # Search
    REINDEX = "REINDEX"
    CLEAR_LRU = "CLEAR_LRU"

    # DB
    INSERT_TRACKS = "INSERT_TRACKS"
    MISSING_AUDIO = "MISSING_AUDIO"
    MISSING_AUDIO_RESPONSE = "MISSING_AUDIO_RESPONSE"
    TRACK_BY_ID = "TRACK_BY_ID"
    TRACK_BY_ID_RESPONSE = "TRACK_BY_ID_RESPONSE"
    TRACK_INCREMENT_FAIL_COUNT = "TRACK_INCREMENT_FAIL_COUNT"
    UPDATE_TRACK_AUDIO = "UPDATE_TRACK_AUDIO"
    UPDATE_TRACK_CACHED = "UPDATE_TRACK_CACHED"
    UPDATE_TRACK_CACHE_STATE = "UPDATE_TRACK_CACHE_STATE"

    # Fetch
    TRIGGER = "TRIGGER"
    LOAD_HOT = "LOAD_HOT"
    RECALC_LUFS = "RECALC_LUFS"
    STATS = "STATS"
    BLACKLIST_CLEAR = "BLACKLIST_CLEAR"
    BLACKLIST_REMOVE = "BLACKLIST_REMOVE"


class PayloadEnvelope(BaseModel):
    """Содержание сообщения"""

    version: int = Field(default=1, ge=1)
    type: str
    data: Any


@dataclass(slots=True, frozen=True)
class ControlMessage:
    """Управляющее сообщение для процесса"""

    # действие для процесса или всех процессов, если имя не указанно
    action: ControlAction
    # имя узла процесса
    node: ControlNode | None = None
    # данные для выполнения действия
    payload: PayloadEnvelope | None = None
    # ид сообщения
    correlation_id: UUID = field(default_factory=uuid4)


@dataclass(slots=True)
class ControlBus:
    """Управляющая шина"""

    _queue: Queue = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self._queue: Queue[ControlMessage] = Queue()

    async def send(self, message: ControlMessage) -> None:
        await self._queue.put(message)

    async def receive(self) -> ControlMessage:
        return await self._queue.get()


@dataclass(slots=True, frozen=True)
class Success:
    message: str

    is_ok: Literal[True] = True


@dataclass(slots=True, frozen=True)
class Error:
    error: str

    is_ok: Literal[False] = False


ControlResult: TypeAlias = Success | Error
