"""
DAG-based async process runner.

- N processes with dependencies (DAG).
- One generic supervision loop per node.
- Exponential backoff with jitter on restarts.
- Graceful handling of SIGINT/SIGTERM.
- Cross-platform signaling.

from manager.runner import Runner, ProcessNode, ProcessSpec, ProcessCmd

def make_cmd_sleep(msg: str, secs: int) -> ProcessCmd:
    import sys
    return ProcessCmd(exe=sys.executable,
    args=["-c", f"import time; print('{msg}'); time.sleep({secs})"])

nodes = [
    ProcessNode(id="A", spec=ProcessSpec(name="A", cmd_factory=lambda: make_cmd_sleep("A", 3600))),
    ProcessNode(id="B", spec=ProcessSpec(name="B",
    cmd_factory=lambda: make_cmd_sleep("B", 3600)), deps={"A"}),
]

runner = Runner(run_id="dev", nodes=nodes)
# asyncio.run(runner.serve_forever())
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import platform
import signal
import sys
import time
from collections import defaultdict, deque

from structlog.typing import FilteringBoundLogger

from manager.logging import get_logger

from .backoff import BackoffPolicy, BackoffState
from .signals import install_signal_handlers
from .types import ManagedProcess, ProcessCmd, ProcessNode, ProcessSpec
from .utils import cancel_task, drain_process_stream, is_process_alive


class Runner:
    """Abstract DAG runner supervising processes as a dependency graph."""

    MAX_LOG_LINE_LEN = 1000  # protect logs

    def __init__(
        self,
        run_id: str,
        nodes: list[ProcessNode],
        *,
        default_backoff: BackoffPolicy | None = None,
    ) -> None:
        self.run_id: str = run_id
        self.log: FilteringBoundLogger = get_logger("runner")

        if not nodes:
            raise ValueError("At least one ProcessNode is required")

        # Index nodes
        self.nodes_by_id: dict[str, ProcessNode] = {n.id: n for n in nodes}
        if len(self.nodes_by_id) != len(nodes):
            raise ValueError("Duplicate node IDs are not allowed")

        # Graph: parents (deps) and children (reverse edges)
        self.parents: dict[str, set[str]] = {n.id: set(n.deps) for n in nodes}
        self.children: dict[str, set[str]] = defaultdict(set)
        for node in nodes:
            for dep in node.deps:
                if dep not in self.nodes_by_id:
                    raise ValueError(f"Unknown dependency: {dep!r} for node {node.id!r}")
                self.children[dep].add(node.id)

        # Topological order (and cycle detection)
        self.topo_order: list[str] = self._toposort(self.parents)
        if len(self.topo_order) != len(nodes):
            raise ValueError("Dependency cycle detected")

        # Backoff state per node
        base_policy = default_backoff or BackoffPolicy()
        self.backoff: dict[str, BackoffState] = {
            nid: BackoffState(base_policy) for nid in self.nodes_by_id
        }

        # Runtime state
        self.shutdown_event: asyncio.Event = asyncio.Event()
        self.ready_event: dict[str, asyncio.Event] = {
            nid: asyncio.Event() for nid in self.nodes_by_id
        }
        self.proc_handles: dict[str, ManagedProcess] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    # ----- Public API ---------------------------------------------------------------------------

    def health(self) -> dict[str, object]:
        """Health snapshot for HTTP /health."""
        nodes_snapshot: dict[str, object] = {}
        for nid, node in self.nodes_by_id.items():
            handle = self.proc_handles.get(nid)
            running = is_process_alive(handle.process) if handle else False
            nodes_snapshot[nid] = {
                "name": node.spec.name,
                "running": running,
                "ready": self.ready_event[nid].is_set(),
                "pid": handle.pid if handle else None,
                "uptime_s": handle.uptime_seconds if handle else 0.0,
                "deps": sorted(self.parents[nid]),
            }
        return {
            "run_id": self.run_id,
            "nodes": nodes_snapshot,
            "shutdown": self.shutdown_event.is_set(),
        }

    def ready(self) -> bool:
        """True when all nodes are 'ready' (probes passed or marked)."""
        return all(evt.is_set() for evt in self.ready_event.values())

    async def serve_forever(self) -> None:
        """Start supervision tasks for all nodes and wait until shutdown."""
        loop = asyncio.get_running_loop()
        install_signal_handlers(loop, self._on_signal)

        # Spawn a supervisor loop per node
        for nid in self.topo_order:
            task = asyncio.create_task(self._supervise_node(nid), name=f"supervise:{nid}")
            self._tasks.add(task)

        self.log.info(
            "runner.started",
            run_id=self.run_id,
            platform=platform.platform(),
            python=sys.version.split()[0],
            node_count=len(self.nodes_by_id),
        )

        try:
            await self.shutdown_event.wait()
        finally:
            await self._graceful_stop_all()
            await self._cancel_all_tasks()
            self.log.info("runner.stopped", run_id=self.run_id)

    async def shutdown(self) -> None:
        """External shutdown trigger (idempotent)."""
        if not self.shutdown_event.is_set():
            self.log.info("runner.shutdown_requested", run_id=self.run_id)
            self.shutdown_event.set()

    # ----- Signal handler -----------------------------------------------------------------------

    def _on_signal(self, received_sig: signal.Signals) -> None:
        self.log.warning("signal.received", run_id=self.run_id, signal=received_sig.name)
        task = asyncio.create_task(self.shutdown())
        self._tasks.add(task)

    # ----- Supervision per node -----------------------------------------------------------------

    async def _supervise_node(self, node_id: str) -> None:
        node_id = str(node_id)
        node = self.nodes_by_id[node_id]
        backoff_state = self.backoff[node_id]
        ready_evt = self.ready_event[node_id]

        while not self.shutdown_event.is_set():
            # 1) Gate: all parents ready
            await self._wait_parents_ready(node_id)
            if self.shutdown_event.is_set():
                break

            # 2) Try start
            handle = await self._start_process(node.spec, backoff_state)
            if handle is None:
                await self.shutdown()
                break

            self.proc_handles[node_id] = handle

            # 3) Mark ready (immediately or via probe)
            await self._mark_ready(node_id)

            # 4) Wait for exit or shutdown
            return_code = await self._wait_or_shutdown(handle.process)
            uptime = handle.uptime_seconds

            # 5) On exit: clear ready; stop all dependents
            ready_evt.clear()
            for child_id in self.children.get(node_id, ()):
                await self._stop_node(child_id, reason=f"{node_id}_down")

            self.log.info(
                "proc.exit",
                run_id=self.run_id,
                node_id=node_id,
                name=node.spec.name,
                pid=handle.pid,
                returncode=return_code,
                uptime_s=round(uptime, 3),
            )

            # 6) Ensure process is stopped and cleanup
            await self._stop_process(
                handle, reason="exit" if not self.shutdown_event.is_set() else "shutdown"
            )
            self.proc_handles.pop(node_id, None)

            # 7) Backoff bookkeeping and retry
            backoff_state.reset_if_uptime_good(uptime)
            if self.shutdown_event.is_set():
                break
            if return_code is not None and return_code == 0:
                # Clean exit without shutdown → treat as restart
                pass
            if backoff_state.too_many_restarts():
                self.log.error(
                    "proc.giveup",
                    run_id=self.run_id,
                    node_id=node_id,
                    name=node.spec.name,
                    reason="too_many_restarts_in_window",
                )
                await self.shutdown()
                break

            delay = backoff_state.next_delay_with_jitter()
            self.log.warning(
                "proc.retry",
                run_id=self.run_id,
                node_id=node_id,
                name=node.spec.name,
                attempt=backoff_state.attempt,
                delay_s=round(delay, 3),
            )
            await asyncio.sleep(delay)

    # ----- Graph helpers ------------------------------------------------------------------------

    @staticmethod
    def _toposort(parents: dict[str, set[str]]) -> list[str]:
        indeg: dict[str, int] = {n: len(deps) for n, deps in parents.items()}
        children: dict[str, set[str]] = defaultdict(set)
        for child, deps in parents.items():
            for p in deps:
                children[p].add(child)
        q: deque[str] = deque([n for n, d in indeg.items() if d == 0])
        order: list[str] = []
        while q:
            n = q.popleft()
            order.append(n)
            for c in children.get(n, ()):
                indeg[c] -= 1
                if indeg[c] == 0:
                    q.append(c)
        return order

    async def _wait_parents_ready(self, node_id: str) -> None:
        parents = self.parents.get(node_id, set())
        if not parents:
            return
        # Wait until all parents are ready (or shutdown).
        while not self.shutdown_event.is_set():
            if all(self.ready_event[p].is_set() for p in parents):
                return
            waits = {asyncio.create_task(self.ready_event[p].wait()) for p in parents}
            waits.add(asyncio.create_task(self.shutdown_event.wait()))
            done, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            for t in pending:
                t.cancel()
            if self.shutdown_event.is_set():
                return

    # ----- Start/Stop & readiness ---------------------------------------------------------------

    async def _start_process(
        self, spec: ProcessSpec, backoff_state: BackoffState
    ) -> ManagedProcess | None:
        if self.shutdown_event.is_set():
            return None

        cmd: ProcessCmd = spec.cmd_factory()
        env = os.environ.copy()
        if cmd.env:
            env.update(cmd.env)
        if spec.env_extra:
            env.update(spec.env_extra)

        popen_kwargs: dict[str, object] = {
            "cwd": cmd.cwd,
            "env": env,
            "stdin": asyncio.subprocess.DEVNULL,
            "stdout": asyncio.subprocess.PIPE,
            "stderr": asyncio.subprocess.PIPE,
        }

        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        else:
            popen_kwargs["creationflags"] = 0x00000200

        try:
            proc = await asyncio.create_subprocess_exec(
                cmd.exe,
                *cmd.args,
                **popen_kwargs,  # type: ignore[arg-type]
            )
        except FileNotFoundError:
            self.log.error(
                "proc.start_error",
                run_id=self.run_id,
                error="FileNotFoundError",
                exe=cmd.exe,
                args=cmd.args,
                name=spec.name,
            )
            return None
        except Exception as exc:
            self.log.error(
                "proc.start_error",
                run_id=self.run_id,
                error=repr(exc),
                name=spec.name,
            )
            return None

        backoff_state.register_start()
        handle = ManagedProcess(
            process_spec=spec,
            process=proc,
            started_monotonic=time.monotonic(),
            stdout_task=asyncio.create_task(
                drain_process_stream(
                    self.log,
                    process_name=spec.name,
                    stream_name="stdout",
                    reader=proc.stdout,
                    max_line_len=self.MAX_LOG_LINE_LEN,
                )
            ),
            stderr_task=asyncio.create_task(
                drain_process_stream(
                    self.log,
                    process_name=spec.name,
                    stream_name="stderr",
                    reader=proc.stderr,
                    max_line_len=self.MAX_LOG_LINE_LEN,
                )
            ),
        )
        self.log.info(
            "proc.started",
            run_id=self.run_id,
            name=spec.name,
            pid=proc.pid,
            cwd=cmd.cwd,
            exe=cmd.exe,
            args=cmd.args,
        )
        return handle

    async def _mark_ready(self, node_id: str) -> None:
        node = self.nodes_by_id[node_id]
        spec = node.spec
        evt = self.ready_event[node_id]
        if spec.ready_probe is None:
            evt.set()
            self.log.info("proc.ready", run_id=self.run_id, node_id=node_id, name=spec.name)
            return
        try:
            ok = await asyncio.wait_for(spec.ready_probe(), timeout=spec.ready_timeout_s)
        except TimeoutError:
            ok = False
        except Exception as exc:
            self.log.warning(
                "proc.ready_probe_error", run_id=self.run_id, node_id=node_id, error=repr(exc)
            )
            ok = False
        if ok:
            evt.set()
            self.log.info("proc.ready", run_id=self.run_id, node_id=node_id, name=spec.name)
        else:
            self.log.warning(
                "proc.ready_timeout",
                run_id=self.run_id,
                node_id=node_id,
                name=spec.name,
                timeout_s=spec.ready_timeout_s,
            )

    async def _stop_node(self, node_id: str, *, reason: str) -> None:
        handle = self.proc_handles.get(node_id)
        if handle is None:
            return
        await self._stop_process(handle, reason=reason)
        self.proc_handles.pop(node_id, None)
        self.ready_event[node_id].clear()

    async def _stop_process(self, handle: ManagedProcess, *, reason: str) -> None:
        process = handle.process
        spec = handle.process_spec

        self._send_terminate(process)
        self.log.info(
            "proc.terminate_sent",
            run_id=self.run_id,
            name=spec.name,
            pid=process.pid,
            reason=reason,
        )

        try:
            await asyncio.wait_for(process.wait(), timeout=spec.stop_timeout_s)
            self.log.info(
                "proc.terminated",
                run_id=self.run_id,
                name=spec.name,
                pid=process.pid,
                returncode=process.returncode,
            )
        except TimeoutError:
            self._send_kill(process)
            self.log.warning("proc.kill_sent", run_id=self.run_id, name=spec.name, pid=process.pid)
            try:
                await asyncio.wait_for(process.wait(), timeout=spec.kill_timeout_s)
            except TimeoutError:
                self.log.error(
                    "proc.kill_timeout", run_id=self.run_id, name=spec.name, pid=process.pid
                )

        await cancel_task(handle.stdout_task)
        await cancel_task(handle.stderr_task)

    # ----- Platform-specific signaling ----------------------------------------------------------

    def _send_terminate(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if os.name == "posix":
                if proc.pid is not None:
                    os.killpg(proc.pid, signal.SIGTERM)  # type: ignore[attr-defined]
            else:
                if proc.pid is not None:
                    try:
                        proc.send_signal(signal.CTRL_BREAK_EVENT)
                    except Exception:
                        proc.terminate()
        except ProcessLookupError:
            pass
        except Exception as exc:
            self.log.warning("signal.term_error", run_id=self.run_id, error=repr(exc))

    def _send_kill(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is not None:
            return
        try:
            if os.name == "posix":
                if proc.pid is not None:
                    os.killpg(proc.pid, signal.SIGKILL)  # type: ignore[attr-defined]
            else:
                proc.kill()
        except ProcessLookupError:
            pass
        except Exception as exc:
            self.log.warning("signal.kill_error", run_id=self.run_id, error=repr(exc))

    # ----- Wait helpers -------------------------------------------------------------------------

    async def _wait_or_shutdown(self, proc: asyncio.subprocess.Process) -> int | None:
        """Wait for process exit or global shutdown; return returncode if exited first."""
        wait_task = asyncio.create_task(proc.wait())
        shutdown_task = asyncio.create_task(self.shutdown_event.wait())
        done, pending = await asyncio.wait(
            {wait_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED
        )
        for t in pending:
            t.cancel()
        if wait_task in done:
            with contextlib.suppress(Exception):
                return wait_task.result()
        return None

    async def _graceful_stop_all(self) -> None:
        # Stop in reverse topological order.
        for nid in reversed(self.topo_order):
            await self._stop_node(nid, reason="shutdown")

    async def _cancel_all_tasks(self) -> None:
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
