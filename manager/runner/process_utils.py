"""
Async utilities for process supervision.

- cancel_task(): safe cancellation of an asyncio.Task
- drain_process_stream(): reads and logs process stdout/stderr line-by-line
- is_process_alive(): cheap check for subprocess liveness
"""

from __future__ import annotations

import asyncio
import contextlib

from structlog.typing import FilteringBoundLogger


async def cancel_task(task: asyncio.Task[None] | None) -> None:
    """Cancel a task and await its completion, suppressing any exceptions."""
    if task is None or task.done():
        return
    task.cancel()
    with contextlib.suppress(Exception):
        await task


async def drain_process_stream(
    logger: FilteringBoundLogger,
    *,
    process_name: str,
    stream_name: str,
    reader: asyncio.StreamReader | None,
    max_line_len: int = 1000,
    extra: dict[str, object] | None = None,
) -> None:
    """Drain an async stream (stdout/stderr) and log each line safely."""
    if reader is None:
        return

    prefix = f"{process_name}.{stream_name}"
    try:
        while not reader.at_eof():
            raw = await reader.readline()
            if not raw:
                break
            try:
                line = raw.decode(errors="replace").rstrip("\r\n")
            except Exception:
                line = repr(raw[:max_line_len])

            if len(line) > max_line_len:
                line = line[:max_line_len] + "…"

            fields: dict[str, object] = {"process": process_name, "stream": prefix, "line": line}
            if extra:
                fields.update(extra)
            logger.debug("proc.out", **fields)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        fields = {"process": process_name, "stream": prefix, "error": repr(exc)}
        if extra:
            fields.update(extra)
        logger.warning("proc.out_error", **fields)
