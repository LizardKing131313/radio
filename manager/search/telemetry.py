from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import cast


def read_youtube_api_telemetry(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return _empty_state(status="unknown")
    except (OSError, json.JSONDecodeError):
        return _empty_state(status="unreadable")
    if not isinstance(raw, dict):
        return _empty_state(status="unreadable")
    return {**_empty_state(status="unknown"), **raw}


def record_youtube_api_success(
    path: Path,
    *,
    estimated_quota_units: int,
    result_count: int,
    now: datetime | None = None,
) -> None:
    state = read_youtube_api_telemetry(path)
    timestamp = (now or datetime.now(UTC)).isoformat()
    state.update(
        {
            "status": "ok",
            "updated_at": timestamp,
            "last_success_at": timestamp,
            "last_error_at": None,
            "last_error": None,
            "last_http_status": None,
            "quota_exhausted": False,
            "consecutive_errors": 0,
            "windows_ok": cast(int, state["windows_ok"]) + 1,
            "result_count": cast(int, state["result_count"]) + result_count,
            "estimated_quota_units": cast(int, state["estimated_quota_units"])
            + estimated_quota_units,
        }
    )
    _write_state(path, state)


def record_youtube_api_error(
    path: Path,
    error: BaseException,
    *,
    now: datetime | None = None,
) -> None:
    state = read_youtube_api_telemetry(path)
    timestamp = (now or datetime.now(UTC)).isoformat()
    status_code = getattr(error, "status_code", None)
    message = str(error)
    state.update(
        {
            "status": "error",
            "updated_at": timestamp,
            "last_error_at": timestamp,
            "last_error": message,
            "last_http_status": status_code,
            "quota_exhausted": is_youtube_quota_error(error),
            "consecutive_errors": cast(int, state["consecutive_errors"]) + 1,
        }
    )
    _write_state(path, state)


def estimate_window_quota_units(window_size: int) -> int:
    pages = max(1, (max(1, window_size) + 49) // 50)
    # search.list стоит 100 units, videos.list с деталями - 1 unit на страницу.
    return pages * 101


def is_youtube_quota_error(error: BaseException) -> bool:
    """Понять, что YouTube отказал именно из-за квоты или rate limit."""
    return _is_quota_error(getattr(error, "status_code", None), str(error))


def _empty_state(*, status: str) -> dict[str, object]:
    return {
        "status": status,
        "updated_at": None,
        "last_success_at": None,
        "last_error_at": None,
        "last_error": None,
        "last_http_status": None,
        "quota_exhausted": False,
        "consecutive_errors": 0,
        "windows_ok": 0,
        "result_count": 0,
        "estimated_quota_units": 0,
    }


def _is_quota_error(status_code: object, message: str) -> bool:
    return status_code in {403, 429} and any(
        marker in message.lower() for marker in ("quota", "rate", "exceeded")
    )


def _write_state(path: Path, state: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    tmp.replace(path)
