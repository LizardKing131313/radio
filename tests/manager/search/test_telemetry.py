from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from manager.search.search_helpers import YouTubeAPIError
from manager.search.telemetry import (
    estimate_window_quota_units,
    is_youtube_quota_error,
    read_youtube_api_telemetry,
    record_youtube_api_error,
    record_youtube_api_success,
)


def test_read_youtube_api_telemetry_defaults_and_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "youtube.json"
    assert read_youtube_api_telemetry(path)["status"] == "unknown"

    path.write_text("{", encoding="utf-8")
    assert read_youtube_api_telemetry(path)["status"] == "unreadable"

    path.write_text("[]", encoding="utf-8")
    assert read_youtube_api_telemetry(path)["status"] == "unreadable"


def test_record_youtube_api_success_accumulates(tmp_path: Path) -> None:
    path = tmp_path / "youtube.json"
    now = datetime(2026, 1, 1, tzinfo=UTC)

    record_youtube_api_success(path, estimated_quota_units=101, result_count=2, now=now)
    record_youtube_api_success(path, estimated_quota_units=202, result_count=3, now=now)
    state = read_youtube_api_telemetry(path)

    assert state["status"] == "ok"
    assert state["windows_ok"] == 2
    assert state["result_count"] == 5
    assert state["estimated_quota_units"] == 303
    assert state["consecutive_errors"] == 0
    assert state["last_success_at"] == now.isoformat()


def test_record_youtube_api_error_marks_quota(tmp_path: Path) -> None:
    path = tmp_path / "youtube.json"
    now = datetime(2026, 1, 1, tzinfo=UTC)

    record_youtube_api_error(
        path,
        YouTubeAPIError("quota exceeded", status_code=403),
        now=now,
    )
    state = read_youtube_api_telemetry(path)

    assert state["status"] == "error"
    assert state["last_http_status"] == 403
    assert state["quota_exhausted"] is True
    assert state["consecutive_errors"] == 1
    assert state["last_error_at"] == now.isoformat()


def test_record_youtube_api_error_without_quota_marker(tmp_path: Path) -> None:
    path = tmp_path / "youtube.json"

    record_youtube_api_error(path, YouTubeAPIError("forbidden", status_code=403))

    assert read_youtube_api_telemetry(path)["quota_exhausted"] is False
    assert is_youtube_quota_error(YouTubeAPIError("forbidden", status_code=403)) is False


def test_estimate_window_quota_units() -> None:
    assert estimate_window_quota_units(0) == 101
    assert estimate_window_quota_units(50) == 101
    assert estimate_window_quota_units(51) == 202
    assert is_youtube_quota_error(YouTubeAPIError("quota exceeded", status_code=403)) is True
