from __future__ import annotations

import json
from pathlib import Path
from typing import Self

import pytest

from manager.search.search_helpers import YouTubeAPIError
from manager.youtube_live import (
    empty_live_state,
    fetch_live_metadata,
    live_refresh_due,
    live_refresh_interval,
    read_live_state,
    refresh_live_metadata,
)


def test_live_state_defaults_and_unreadable(tmp_path: Path) -> None:
    path = tmp_path / "live.json"
    assert empty_live_state()["status"] == "disabled"
    assert read_live_state(path)["status"] == "unknown"
    path.write_text("not-json", encoding="utf-8")
    assert read_live_state(path)["status"] == "unreadable"


def test_live_refresh_schedule_requires_id_and_minimum_interval() -> None:
    assert live_refresh_interval(0) == 1
    assert live_refresh_interval(60) == 60
    assert live_refresh_due("video", 10, 10)
    assert not live_refresh_due("video", 9, 10)
    assert not live_refresh_due("", 10, 0)


def test_refresh_preserves_last_state_on_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "live.json"
    path.write_text(json.dumps({"status": "ok", "title": "old"}), encoding="utf-8")
    monkeypatch.setattr(
        "manager.youtube_live.fetch_live_metadata",
        lambda _video_id, _api_key: (_ for _ in ()).throw(YouTubeAPIError("offline")),
    )
    state = refresh_live_metadata(path, "video", "key")
    assert state["status"] == "stale"
    assert state["title"] == "old"
    assert path.exists()


def test_fetch_normalizes_video_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "items": [
                        {
                            "snippet": {"title": "Live", "channelTitle": "Radio"},
                            "liveStreamingDetails": {"actualStartTime": "now"},
                            "status": {"uploadStatus": "processed"},
                        }
                    ]
                }
            ).encode()

    monkeypatch.setattr("manager.youtube_live.urlopen", lambda *_args, **_kwargs: Response())
    state = fetch_live_metadata("video", "key")
    assert state["title"] == "Live"
    assert state["channel"] == "Radio"
    assert state["actual_start_time"] == "now"


def test_fetch_rejects_missing_video(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"items": []}'

    monkeypatch.setattr("manager.youtube_live.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(YouTubeAPIError):
        fetch_live_metadata("missing", "key")


def test_fetch_wraps_transport_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise OSError("offline")

    monkeypatch.setattr("manager.youtube_live.urlopen", fail)
    with pytest.raises(YouTubeAPIError, match="offline"):
        fetch_live_metadata("video", "key")


def test_fetch_wraps_malformed_response(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self) -> bytes:
            return b"not-json"

    monkeypatch.setattr("manager.youtube_live.urlopen", lambda *_args, **_kwargs: Response())
    with pytest.raises(YouTubeAPIError, match="Expecting value"):
        fetch_live_metadata("video", "key")
