from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from abc import ABC
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypedDict

from structlog.typing import FilteringBoundLogger

from manager.runner.control import ControlResult, Error, Success
from manager.runner.node import NodeHandle, Runnable
from manager.runner.process_utils import drain_process_stream


@dataclass(slots=True, frozen=True)
class ProcessCommand:
    """External process start specification."""

    exe: str
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] | None = None


@dataclass(slots=True)
class ProcessHandle(NodeHandle):
    runnable: ProcessRunnable
    process: asyncio.subprocess.Process
    stdout_task: asyncio.Task[None] | None
    stderr_task: asyncio.Task[None] | None
    started_monotonic: float

    @property
    def pid(self) -> int | None:
        return self.process.pid

    @property
    def is_alive(self) -> bool:
        return self.process is not None and self.process.returncode is None


class PopenKwargs(TypedDict, total=False):
    stdin: int | None
    stdout: int | None
    stderr: int | None
    cwd: str | Path | None
    env: Mapping[str, str] | None
    start_new_session: bool


@dataclass(slots=True)
class ProcessRunnable(Runnable, ABC):
    """Runnable that manages an external OS process (protocol-agnostic)."""

    # hard kill wait after SIGKILL
    kill_timeout_sec: float = 2.0
    # extra env
    env_extra: dict[str, str] = field(default_factory=dict)

    # output line clamp for process stdout/stderr
    MAX_LOG_LINE_LEN = 1000

    # --- must be implemented in subclass ---------------------------------------------------------
    @property
    def command(self) -> ProcessCommand:
        raise NotImplementedError

    # --- lifecycle --------------------------------------------------------------------------------

    async def start(
        self, log_event: FilteringBoundLogger, log_out: FilteringBoundLogger
    ) -> NodeHandle | None:
        """Spawn process and start drainers."""
        env = os.environ.copy()
        if self.command.env:
            env.update(self.command.env)
        if self.env_extra:
            env.update(self.env_extra)

        popen_kwargs: PopenKwargs = {
            "cwd": self.command.cwd,
            "env": env,
            "stdin": asyncio.subprocess.DEVNULL,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
            "start_new_session": True,
        }

        try:
            process = await asyncio.create_subprocess_exec(
                self.command.exe,
                *self.command.args,
                **popen_kwargs,
            )
        except FileNotFoundError:
            log_event.error(
                "proc.start_error",
                error="FileNotFoundError",
                exe=self.command.exe,
                args=self.command.args,
            )
            return None
        except Exception as exc:
            log_event.error("proc.start_error", error=repr(exc))
            return None

        self.backoff_state.register_start()

        handle = ProcessHandle(
            runnable=self,
            process=process,
            started_monotonic=time.monotonic(),
            stdout_task=asyncio.create_task(
                drain_process_stream(
                    log_out,
                    process_name=self.name,
                    stream_name="stdout",
                    reader=process.stdout,
                    max_line_len=self.MAX_LOG_LINE_LEN,
                    extra={"node_id": self.node_id, "name": self.name},
                ),
                name=f"drain:{self.node_id}:stdout",
            ),
            stderr_task=asyncio.create_task(
                drain_process_stream(
                    log_out,
                    process_name=self.name,
                    stream_name="stderr",
                    reader=process.stderr,
                    max_line_len=self.MAX_LOG_LINE_LEN,
                    extra={"node_id": self.node_id, "name": self.name},
                ),
                name=f"drain:{self.node_id}:stderr",
            ),
        )

        log_event.info(
            "proc.started",
            pid=process.pid,
            cwd=self.command.cwd,
            exe=self.command.exe,
            args=self.command.args,
        )
        return handle

    async def mark_ready(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        ready_message = "process ready"
        ready_action = self._get_ready_action()
        if ready_action is None:
            ready_event.set()
            log_event.info(ready_message)
            return Success(ready_message)

        try:
            result = await asyncio.wait_for(ready_action(), timeout=self.ready_timeout_sec)
        except (asyncio.TimeoutError, OSError, ConnectionError):  # noqa: UP041
            result = Error("timeout error")
        except Exception as exception:
            error_message = "ready action error"
            log_event.warning(error_message, error=repr(exception))
            result = Error(error_message)

        if result.is_ok:
            ready_event.set()
            log_event.info(ready_message)
        else:
            log_event.warning("process ready timeout", timeout_s=self.ready_timeout_sec)

        return result

    async def wait_or_shutdown(
        self, handle: NodeHandle, shutdown_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> int | None:
        """Wait until process exits or shutdown requested."""
        assert isinstance(handle, ProcessHandle)

        proc_wait = asyncio.create_task(handle.process.wait(), name=f"wait:{handle.pid}")
        shut_wait = asyncio.create_task(shutdown_event.wait(), name="wait:shutdown")

        done, pending = await asyncio.wait(
            {proc_wait, shut_wait}, return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        # дождаться отмены — не даём CancelledError всплыть наружу
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if proc_wait in done:
            return handle.process.returncode

        # stop() сам корректно гасит отмены; на всякий случай ловим CancelledError
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await self.stop(handle, reason="shutdown", log_event=log_event)
        return None

    async def stop(self, handle: NodeHandle, reason: str, log_event: FilteringBoundLogger) -> None:
        """Generic stop: TERM(process group) → wait → KILL(process group) → wait → stop drainers."""
        assert isinstance(handle, ProcessHandle)
        process = handle.process

        # 1) TERM whole process group
        if process.returncode is None:
            try:
                if process.pid is not None:
                    try:
                        pgid = os.getpgid(process.pid)  # type: ignore[attr-defined]
                    except Exception:
                        pgid = process.pid
                    os.killpg(pgid, signal.SIGTERM)  # type: ignore[attr-defined]
            except Exception as exc:
                log_event.warning("signal.term_error", error=repr(exc))

        log_event.info("proc.terminate_sent", pid=process.pid, reason=reason)

        # 2) wait for graceful exit
        try:
            await asyncio.wait_for(process.wait(), timeout=self.stop_timeout_sec)
            log_event.info("proc.terminated", pid=process.pid, returncode=process.returncode)
        except asyncio.TimeoutError:  # noqa: UP041
            # 3) KILL whole process group
            try:
                if process.pid is not None:
                    try:
                        pgid = os.getpgid(process.pid)  # type: ignore[attr-defined]
                    except Exception:
                        pgid = process.pid
                    os.killpg(pgid, signal.SIGKILL)  # type: ignore[attr-defined]
            except Exception as exc:
                log_event.warning("signal.kill_error", error=repr(exc))

            # 4) final wait after KILL
            try:
                await asyncio.wait_for(process.wait(), timeout=self.kill_timeout_sec)
                log_event.info("proc.killed", pid=process.pid, returncode=process.returncode)
            except asyncio.TimeoutError:  # noqa: UP041
                log_event.error("proc.kill_timeout", pid=process.pid)

        # 5) stop log drainers — отменяем и безопасно ждём завершения
        drainers = [t for t in (handle.stdout_task, handle.stderr_task) if t]
        for t in drainers:
            t.cancel()
        if drainers:
            results = await asyncio.gather(*drainers, return_exceptions=True)
            # опционально: залогировать неожиданные ошибки
            for result in results:
                if isinstance(result, Exception) and not isinstance(result, asyncio.CancelledError):
                    log_event.warning("drainer.error", error=repr(result))
