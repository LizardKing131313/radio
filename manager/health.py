from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from manager.config import AppConfig


def heartbeat_path(config: AppConfig, name: str) -> Path:
    return config.paths.runtime_info_dir / "health" / f"{name}.json"


def write_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps({"updated_at": datetime.now(UTC).isoformat()}),
        encoding="utf-8",
    )
    temporary.replace(path)


def is_fresh(path: Path, max_age_sec: int, *, now: float | None = None) -> bool:
    try:
        age = (now if now is not None else time.time()) - path.stat().st_mtime
    except FileNotFoundError:
        return False
    return 0 <= age <= max(1, max_age_sec)


def newest_mtime(root: Path, pattern: str) -> float | None:
    newest: float | None = None
    for path in root.rglob(pattern):
        mtime = path.stat().st_mtime
        newest = mtime if newest is None else max(newest, mtime)
    return newest


def check_component(
    config: AppConfig, component: str, max_age_sec: int, *, now: float | None = None
) -> bool:
    timestamp = now if now is not None else time.time()
    if component in {"search", "prefetch", "queue-player"}:
        return is_fresh(heartbeat_path(config, component), max_age_sec, now=timestamp)
    if component == "liquidsoap":
        return is_fresh(
            config.paths.nowplaying_path.with_suffix(".txt.kv"), max_age_sec, now=timestamp
        )
    if component == "ffmpeg":
        mtime = newest_mtime(config.paths.www_hls_ts, "index.m3u8")
        return mtime is not None and timestamp - mtime <= max(1, max_age_sec)
    raise ValueError(f"unknown health component: {component}")
