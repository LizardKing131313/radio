from __future__ import annotations

import asyncio
import contextlib
import platform
import signal
import sys
from collections import defaultdict, deque
from typing import Any

from structlog.contextvars import bind_contextvars
from structlog.typing import FilteringBoundLogger

from manager.logger import get_logger

from .control import ControlBus, ControlNode, ControlResult, Error
from .node import Node, NodeHandle
from .signals import install_signal_handlers


class Runner:
    def __init__(self, run_id: str, control_bus: ControlBus, nodes: list[Node]) -> None:
        if not nodes:
            raise ValueError("At least one Node is required")

        self._control_bus = control_bus
        self._kick_event: asyncio.Event = asyncio.Event()
        # Context: propagate run_id to all tasks created after this point
        self._run_id: str = run_id
        bind_contextvars(run_id=self._run_id)

        # Dedicated loggers
        self.log_event: FilteringBoundLogger = get_logger("proc.event")
        self.log_out: FilteringBoundLogger = get_logger("proc.out")

        # Index nodes
        self._node_map: dict[ControlNode, Node] = {node.id: node for node in nodes}
        if len(self._node_map) != len(nodes):
            raise ValueError("Duplicate node IDs are not allowed")

        # Graph: parents (deps) and children (reverse edges)
        self._parents: dict[ControlNode, set[ControlNode]] = {
            node.id: set(node.parent) for node in nodes
        }
        self._children: dict[ControlNode, set[ControlNode]] = defaultdict(set)
        for node in nodes:
            for dependency in node.parent:
                if dependency not in self._node_map:
                    raise ValueError(f"Unknown dependency: {dependency!r} for node {node.id!r}")
                self._children[dependency].add(node.id)

        # Topological order (and cycle detection)
        self._order: list[ControlNode] = self._toposort(self._parents)
        if len(self._order) != len(nodes):
            raise ValueError("Dependency cycle detected")

        # Runtime state
        self.shutdown_event: asyncio.Event = asyncio.Event()
        self.ready_event_map: dict[ControlNode, asyncio.Event] = {
            node_id: asyncio.Event() for node_id in self._node_map
        }

        self._handle_map: dict[ControlNode, NodeHandle] = {}
        self._tasks: set[asyncio.Task[object]] = set()

    def health(self) -> dict[str, object]:
        """Health snapshot for HTTP /health."""
        nodes_snapshot: dict[ControlNode, object] = {}
        for node_id, node in self._node_map.items():
            handle = self._handle_map.get(node_id)
            running = handle.is_alive if handle else False
            nodes_snapshot[node_id] = {
                "name": node.runnable.name,
                "running": running,
                "ready": self.ready_event_map[node_id].is_set(),
                "pid": handle.pid if handle else None,
                "uptime_sec": handle.uptime_seconds if handle else 0.0,
                "parent": sorted(self._parents[node_id]),
            }
        return {
            "run_id": self._run_id,
            "nodes": nodes_snapshot,
            "shutdown": self.shutdown_event.is_set(),
        }

    def ready(self) -> bool:
        """True when all nodes are 'ready' (probes passed or marked)."""
        return all(event.is_set() for event in self.ready_event_map.values())

    def _track_task(self, task: asyncio.Task[Any]) -> None:
        """Отслеживать таски и логировать необработанные исключения"""
        self._tasks.add(task)

        def _done(tracked_task: asyncio.Task[Any]) -> None:
            self._tasks.discard(tracked_task)
            if tracked_task.cancelled():
                return
            exception = tracked_task.exception()
            if exception is not None:
                self.log_event.error(
                    "task.unhandled_exception", task=tracked_task.get_name(), error=str(exception)
                )

        task.add_done_callback(_done)

    async def execute(self) -> None:
        """Start supervision tasks for all nodes and wait until shutdown."""
        loop = asyncio.get_running_loop()
        install_signal_handlers(loop, self._on_signal)

        # Spawn a supervisor loop per node
        for node_id in self._order:
            task = asyncio.create_task(self._supervise_node(node_id), name=f"supervise:{node_id}")
            self._track_task(task)

        self.log_event.info(
            "runner.started",
            platform=platform.platform(),
            python=sys.version.split()[0],
            node_count=len(self._node_map),
        )

        # 2) Главный цикл: гонка между shutdown и приёмом control-сообщения.
        try:
            while not self.shutdown_event.is_set():
                receive_task: asyncio.Task[Any] = asyncio.create_task(
                    self._control_bus.receive(), name="control.receive"
                )
                stop_task: asyncio.Task[Any] = asyncio.create_task(
                    self.shutdown_event.wait(), name="runner.shutdown_wait"
                )

                done, pending = await asyncio.wait(
                    {receive_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
                )

                # Не допустить утечек тасок
                for task in pending:
                    task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await task

                # Если пришёл shutdown — выходим
                if stop_task in done and self.shutdown_event.is_set():
                    break

                # Обработка control-сообщения
                if receive_task in done:
                    message = receive_task.result()
                    self.log_event.debug(
                        "received message", action=message.action, node=message.node
                    )
                    if message is None:
                        # Например: bus закрылся. Выходим в shutdown.
                        self.log_event.warning("control.receive_none")
                        self.shutdown_event.set()
                        break

                    node_id = message.node
                    if node_id is None:
                        self.log_event.warning(
                            "control.message_without_node",
                            action=message.action,
                            correlation_id=message.correlation_id,
                        )
                        continue

                    node = self._node_map.get(node_id)
                    if node is None:
                        self.log_event.warning(
                            "control.unknown_node",
                            node=node_id,
                            action=message.action,
                            correlation_id=message.correlation_id,
                        )
                        continue

                    ready_event = self.ready_event_map.get(node_id)
                    if ready_event is None:
                        self.log_event.error(
                            "control.no_ready_event",
                            node=node_id,
                            action=message.action,
                            correlation_id=message.correlation_id,
                        )
                        continue

                    try:
                        await node.runnable.receive(
                            ready_event=ready_event,
                            message=message,
                            log_event=self.log_event,
                        )
                    except Exception as exception:
                        # Не роняем раннер из-за одной ноды/команды
                        self.log_event.error(
                            "control.dispatch_failed",
                            node=node_id,
                            action=message.action,
                            error=str(exception),
                            correlation_id=message.correlation_id,
                        )
        finally:
            # 3) Корректная остановка
            with contextlib.suppress(Exception):
                await self._graceful_stop_all()
            with contextlib.suppress(Exception):
                await self._cancel_all_tasks()
            self.log_event.info("runner.stopped")

    async def shutdown(self) -> None:
        """External shutdown trigger (idempotent)."""
        if not self.shutdown_event.is_set():
            self.log_event.info("runner.shutdown_requested")
            self.shutdown_event.set()

    def _on_signal(self, received_sig: signal.Signals) -> None:
        self.log_event.warning("signal.received", signal=received_sig.name)
        task = asyncio.create_task(self.shutdown())
        self._tasks.add(task)
        self._kick_event.set()

    async def _supervise_node(self, node_id: ControlNode) -> None:
        node = self._node_map[node_id]
        backoff_state = node.runnable.backoff_state
        ready_event = self.ready_event_map[node_id]

        # Bind per-node context for all logs below
        node_log_event = self.log_event.bind(node_id=node_id, name=node.runnable.name)
        node_log_out = self.log_out.bind(node_id=node_id, name=node.runnable.name)

        while not self.shutdown_event.is_set():
            # 1) Gate: all parents ready
            await self._wait_parents_ready(node_id)
            if self.shutdown_event.is_set():
                break

            # 2) Try start
            handle = await node.runnable.start(node_log_event, node_log_out)
            if handle is None:
                await self.shutdown()
                break

            self._handle_map[node_id] = handle

            # 3) Mark ready (immediately or via probe)
            await node.runnable.mark_ready(ready_event, node_log_event)

            # 3.1) Start periodic health-check watchdog (optional)
            health_task: asyncio.Task[Any] | None = None
            interval_sec = node.runnable.health_interval_sec
            threshold = node.runnable.health_fail_threshold
            if interval_sec > 0.0 and threshold > 0:
                health_task = asyncio.create_task(
                    self._health_watchdog(
                        node_id, ready_event, node_log_event, interval_sec, threshold
                    ),
                    name=f"health:{node_id}",
                )
                self._track_task(health_task)

            # 4) Wait for exit or shutdown
            return_code = await node.runnable.wait_or_shutdown(
                handle, shutdown_event=self.shutdown_event, log_event=node_log_event
            )
            uptime = handle.uptime_seconds

            # 5) On exit: clear ready; stop all dependents
            ready_event.clear()
            for child_id in self._children.get(node_id, ()):
                await self._stop_node(child_id, reason=f"{node_id}_down")

            node_log_event.info(
                "proc.exit",
                pid=handle.pid,
                returncode=return_code,
                uptime_s=round(uptime, 3),
            )

            # 6) Ensure process is stopped and cleanup
            # Stop health task first (so оно не дёргало check во время стопа)
            if health_task:
                health_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await health_task
                # noinspection PyUnusedLocal
                health_task = None

            await node.runnable.stop(handle, "exit", node_log_event)
            self._handle_map.pop(node_id, None)

            # 7) Backoff bookkeeping and retry
            backoff_state.reset_if_uptime_good(uptime)
            if self.shutdown_event.is_set():
                break
            if return_code is not None and return_code == 0:
                # Clean exit without shutdown → treat as restart
                pass
            if backoff_state.too_many_restarts():
                node_log_event.error("proc.giveup", reason="too_many_restarts_in_window")
                await self.shutdown()
                break

            delay = backoff_state.next_delay_with_jitter()
            node_log_event.warning(
                "proc.retry", attempt=backoff_state.attempt, delay_s=round(delay, 3)
            )
            await asyncio.sleep(delay)

    async def stop(self, reason: str = "manual") -> None:
        """Gracefully request shutdown (idempotent)."""
        if self.shutdown_event.is_set():
            return
        self.log_event.info("runner.stop_requested", reason=reason)
        self.shutdown_event.set()
        # пнуть всех, кто ждёт родителей/контроля
        self._kick_event.set()

    # ----- Graph helpers ------------------------------------------------------------------------

    @staticmethod
    def _toposort(dependencies_by_node: dict[ControlNode, set[ControlNode]]) -> list[ControlNode]:
        """
        Perform a topological sort.

        Args:
            dependencies_by_node: mapping of node -> set of nodes it depends on.
                Example: {"ffmpeg": {"liquidsoap"}, "liquidsoap": set()}

        Returns:
            A list of nodes in dependency-safe order (parents before dependents).

        Raises:
            ValueError: if the graph contains a cycle.
        """
        # Нормализуем множество всех узлов: и ключи, и упомянутые зависимости
        all_nodes: set[ControlNode] = set(dependencies_by_node.keys())
        for deps in dependencies_by_node.values():
            all_nodes.update(deps)

        # Заполним пустые зависимости для упомянутых, но не объявленных узлов
        normalized_dependencies: dict[ControlNode, set[ControlNode]] = {
            node: set(dependencies_by_node.get(node, set())) for node in all_nodes
        }

        # Подсчёт входящих рёбер (indegree) и таблица зависимых (children)
        inbound_edge_count: dict[ControlNode, int] = {
            node: len(parents) for node, parents in normalized_dependencies.items()
        }
        dependents_by_node: dict[ControlNode, set[ControlNode]] = defaultdict(set)
        for node, parents in normalized_dependencies.items():
            for parent in parents:
                dependents_by_node[parent].add(node)

        # Очередь узлов, готовых к запуску (без входящих рёбер)
        ready_queue: deque[ControlNode] = deque(
            [node for node, count in inbound_edge_count.items() if count == 0]
        )

        order: list[ControlNode] = []
        while ready_queue:
            node = ready_queue.popleft()
            order.append(node)

            for dependent in dependents_by_node.get(node, ()):
                inbound_edge_count[dependent] -= 1
                if inbound_edge_count[dependent] == 0:
                    ready_queue.append(dependent)

        # Если не все узлы были упорядочены — значит цикл
        if len(order) != len(all_nodes):
            raise ValueError("Graph contains a cycle")

        return order

    async def _wait_parents_ready(self, node_id: ControlNode) -> None:
        parents = self._parents.get(node_id, set())
        if not parents:
            return

        # Wait until all parents are ready (or shutdown).
        while not self.shutdown_event.is_set():
            if self._node_map[node_id].disabled:
                return  # включат — цикл начнет заново

            if all(self.ready_event_map[parent].is_set() for parent in parents):
                return

            waits = {asyncio.create_task(self.ready_event_map[parent].wait()) for parent in parents}
            waits.add(asyncio.create_task(self._kick_event.wait()))
            waits.add(asyncio.create_task(self.shutdown_event.wait()))
            _, pending = await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            self._kick_event.clear()

    async def _stop_node(self, node_id: ControlNode, *, reason: str) -> None:
        node = self._node_map.get(node_id)
        if node is None:
            return
        handle = self._handle_map.get(node_id)
        if handle is None:
            return

        node_log_event = self.log_event.bind(node_id=node_id, name=node.runnable.name)
        await node.runnable.stop(handle, reason=reason, log_event=node_log_event)

    async def _graceful_stop_all(self) -> None:
        # Stop in reverse topological order.
        for node_id in reversed(self._order):
            await self._stop_node(node_id, reason="shutdown")

    async def _cancel_all_tasks(self) -> None:
        if not self._tasks:
            return
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def _health_watchdog(
        self,
        node_id: ControlNode,
        ready_event: asyncio.Event,
        log_event: FilteringBoundLogger,
        interval_s: float,
        fail_threshold: int,
    ) -> None:
        """
        Periodically calls runnable.check(). If it fails `fail_threshold` times in a row,
        stops the node with reason='healthcheck_failed' (triggering normal restart/backoff).
        """
        node = self._node_map[node_id]
        fails = 0
        while not self.shutdown_event.is_set():
            await asyncio.sleep(interval_s)
            handle = self._handle_map.get(node_id)

            if handle is None or not handle.is_alive:
                return

            result: ControlResult = Error("check error")
            try:
                result = await node.runnable.check(ready_event=ready_event, log_event=log_event)
            except Exception as exception:
                log_event.warning("health.check_exception", error=repr(exception))

            if result.is_ok:
                if fails:
                    log_event.info("health.ok_after_fail", consecutive_fails=fails)
                fails = 0
                continue

            fails += 1
            log_event.warning("health.fail", consecutive_fails=fails, threshold=fail_threshold)
            if fails >= fail_threshold:
                handle = self._handle_map.get(node_id)
                if handle is not None:
                    try:
                        await node.runnable.stop(
                            handle, reason="healthcheck_failed", log_event=log_event
                        )
                    except Exception as exc:
                        log_event.error("health.stop_failed", error=repr(exc))
                return
