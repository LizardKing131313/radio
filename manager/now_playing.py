from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from manager.config import AppConfig


def current_snapshot(config: AppConfig, *, now: datetime | None = None) -> dict[str, object | None]:
    timestamp = now or datetime.now(UTC)
    source = _read_source(config.paths.nowplaying_path)
    offset_sec = _hls_live_offset_sec(config)
    if source is None:
        return {
            "source": None,
            "hls": {
                "live_offset_sec": offset_sec,
                "age_sec": None,
                "estimated_audible_at": None,
                "is_probably_audible": False,
            },
        }

    kv_path = config.paths.nowplaying_path.with_name(config.paths.nowplaying_path.name + ".kv")
    updated_at = _mtime(kv_path)
    if updated_at is None:
        updated_at = _mtime(config.paths.nowplaying_path)
    if updated_at is None:
        updated_at = timestamp

    estimated_audible_at = updated_at + timedelta(seconds=offset_sec)
    age_sec = max(0, int((timestamp - updated_at).total_seconds()))
    return {
        "source": {**source, "updated_at": updated_at.isoformat()},
        "hls": {
            "live_offset_sec": offset_sec,
            "age_sec": age_sec,
            "estimated_audible_at": estimated_audible_at.isoformat(),
            "is_probably_audible": timestamp >= estimated_audible_at,
        },
    }


def _read_source(path: Path) -> dict[str, str | None] | None:
    kv = _read_kv(path.with_name(path.name + ".kv"))
    line = _read_line(path)
    if kv is None and line is None:
        return None
    return {
        "title": kv.get("title") if kv is not None else None,
        "artist": kv.get("artist") if kv is not None else None,
        "album": kv.get("album") if kv is not None else None,
        "line": line,
    }


def _read_kv(path: Path) -> dict[str, str] | None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return None
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator and key:
            values[key] = value
    return values or None


def _read_line(path: Path) -> str | None:
    try:
        line = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return None
    return line or None


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, UTC)
    except FileNotFoundError:
        return None


def _hls_live_offset_sec(config: AppConfig) -> int:
    # Типичный HLS-клиент слушает не live edge, а несколько сегментов позади.
    return max(1, config.hls.hls_time) * max(1, min(3, config.hls.hls_list_size))
