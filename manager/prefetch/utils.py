from __future__ import annotations

import asyncio
import time
from collections.abc import Iterable
from pathlib import Path


def iter_files(dir_path: Path) -> Iterable[Path]:
    if not dir_path.exists():
        return []
    return (p for p in dir_path.iterdir() if p.is_file())


def watch_url(yid: str) -> str:
    return f"https://www.youtube.com/watch?v={yid}"


async def proc_exec(*args: str, timeout: int | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:  # noqa: UP041
        with SuppressTask():
            proc.kill()
        raise
    return (
        int(proc.returncode or 0),
        out_b.decode("utf-8", "ignore"),
        err_b.decode("utf-8", "ignore"),
    )


class SuppressTask:
    def __enter__(self) -> SuppressTask:
        return self

    def __exit__(self, *_) -> bool:  # noqa: ANN002
        return True


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def iso_after_minutes(minutes: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() + 60 * minutes))
