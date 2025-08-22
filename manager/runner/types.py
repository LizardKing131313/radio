"""
Type definitions for the DAG-based process runner.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field


# Command specification for a process.
@dataclass(slots=True)
class ProcessCmd:
    exe: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] | None = None


ReadyProbe = Callable[[], Awaitable[bool]]  # Async "is ready?" probe.


# Process settings and lifecycle parameters.
@dataclass(slots=True)
class ProcessSpec:
    name: str
    cmd_factory: Callable[[], ProcessCmd]
    ready_probe: ReadyProbe | None = None
    ready_timeout_s: float = 20.0
    stop_timeout_s: float = 8.0
    kill_timeout_s: float = 2.0
    env_extra: dict[str, str] = field(default_factory=dict)


# Live process handle and its stdout/stderr drainers.
@dataclass(slots=True)
class ManagedProcess:
    process_spec: ProcessSpec
    process: asyncio.subprocess.Process
    started_monotonic: float
    stdout_task: asyncio.Task[None] | None
    stderr_task: asyncio.Task[None] | None

    @property
    def pid(self) -> int | None:
        return self.process.pid

    @property
    def uptime_seconds(self) -> float:
        import time

        return max(0.0, time.monotonic() - self.started_monotonic)


# Node in the dependency graph.
@dataclass(slots=True)
class ProcessNode:
    id: str
    spec: ProcessSpec
    deps: set[str] = field(default_factory=set)  # IDs this node depends on.
