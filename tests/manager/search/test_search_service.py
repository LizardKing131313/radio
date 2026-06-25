from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr

from manager.config import AppConfig
from manager.search import search_service
from manager.search.search_helpers import SearchPage, YouTubeAPIError
from manager.search.search_service import _next_sleep_sec, _startup_sleep_sec, search_once
from manager.search.telemetry import (
    read_youtube_api_telemetry,
    record_youtube_api_error,
    record_youtube_api_success,
)


def test_next_sleep_sec_uses_regular_interval_without_quota() -> None:
    cfg = AppConfig()
    cfg.search.interval_sec = 60
    cfg.search.quota_backoff_sec = 21600

    assert _next_sleep_sec(cfg) == 60
    assert _next_sleep_sec(cfg, YouTubeAPIError("temporary", status_code=500)) == 60


def test_next_sleep_sec_uses_quota_backoff_for_quota_errors() -> None:
    cfg = AppConfig()
    cfg.search.interval_sec = 60
    cfg.search.quota_backoff_sec = 21600

    assert _next_sleep_sec(cfg, YouTubeAPIError("quota exceeded", status_code=403)) == 21600


def test_startup_sleep_uses_recent_success(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.paths.youtube_telemetry_path = tmp_path / "youtube.json"
    cfg.search.interval_sec = 60
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record_youtube_api_success(
        cfg.paths.youtube_telemetry_path,
        estimated_quota_units=101,
        result_count=1,
        now=now - timedelta(seconds=10),
    )

    assert _startup_sleep_sec(cfg, now=now) == 50


def test_startup_sleep_uses_quota_backoff(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.paths.youtube_telemetry_path = tmp_path / "youtube.json"
    cfg.search.interval_sec = 60
    cfg.search.quota_backoff_sec = 21600
    now = datetime(2026, 1, 1, tzinfo=UTC)
    record_youtube_api_error(
        cfg.paths.youtube_telemetry_path,
        YouTubeAPIError("quota exceeded", status_code=403),
        now=now - timedelta(seconds=10),
    )

    assert _startup_sleep_sec(cfg, now=now) == 21590


async def test_search_once_uses_persisted_page_token(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppConfig()
    cfg.paths.youtube_telemetry_path = tmp_path / "youtube.json"
    cfg.search.window_size = 50
    cfg.search.max_windows_per_tick = 2
    record_youtube_api_success(
        cfg.paths.youtube_telemetry_path,
        estimated_quota_units=101,
        result_count=0,
        next_page_token="saved-token",
    )
    calls: list[str | None] = []
    pages = [
        SearchPage(
            tracks=[
                {
                    "youtube_id": "youtube0001",
                    "title": "Track",
                    "duration_sec": 120,
                    "url": "https://youtu.be/x",
                }
            ],
            next_page_token="next-token",
            raw_count=1,
        ),
        SearchPage(tracks=[], next_page_token=None, raw_count=1),
    ]

    def fake_search_title_page(
        _title: str,
        _api_key: str,
        _max_results: int,
        page_token: str | None = None,
    ) -> SearchPage:
        calls.append(page_token)
        return pages.pop(0)

    class FakeRepo:
        def __init__(self) -> None:
            self.upserts: list[dict[str, object]] = []

        def upsert(self, **kwargs: object) -> int:
            self.upserts.append(kwargs)
            return len(self.upserts)

    class FakeLog:
        def debug(self, *_args: object, **_kwargs: object) -> None:
            return None

    cfg.secrets.youtube_api_key_raw = SecretStr("key")
    repo = FakeRepo()
    monkeypatch.setattr(search_service, "search_title_page", fake_search_title_page)

    assert await search_once(cfg, repo, FakeLog()) == 1  # type: ignore[arg-type]
    assert calls == ["saved-token", "next-token"]
    assert repo.upserts[0]["youtube_id"] == "youtube0001"
    assert read_youtube_api_telemetry(cfg.paths.youtube_telemetry_path)["next_page_token"] is None


async def test_search_once_expands_large_window_across_youtube_pages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = AppConfig()
    cfg.paths.youtube_telemetry_path = tmp_path / "youtube.json"
    cfg.search.window_size = 120
    cfg.search.max_windows_per_tick = 1
    cfg.secrets.youtube_api_key_raw = SecretStr("key")
    calls: list[tuple[int, str | None]] = []
    pages = [
        SearchPage(
            tracks=[
                {
                    "youtube_id": "youtube0001",
                    "title": "Track 1",
                    "duration_sec": 120,
                    "url": "https://youtu.be/1",
                }
            ],
            next_page_token="page-2",
            raw_count=50,
        ),
        SearchPage(
            tracks=[
                {
                    "youtube_id": "youtube0002",
                    "title": "Track 2",
                    "duration_sec": 121,
                    "url": "https://youtu.be/2",
                }
            ],
            next_page_token="page-3",
            raw_count=50,
        ),
        SearchPage(
            tracks=[
                {
                    "youtube_id": "youtube0003",
                    "title": "Track 3",
                    "duration_sec": 122,
                    "url": "https://youtu.be/3",
                }
            ],
            next_page_token="page-4",
            raw_count=20,
        ),
    ]

    def fake_search_title_page(
        _title: str,
        _api_key: str,
        max_results: int,
        page_token: str | None = None,
    ) -> SearchPage:
        calls.append((max_results, page_token))
        return pages.pop(0)

    class FakeRepo:
        def __init__(self) -> None:
            self.upserts: list[dict[str, object]] = []

        def upsert(self, **kwargs: object) -> int:
            self.upserts.append(kwargs)
            return len(self.upserts)

    class FakeLog:
        def debug(self, *_args: object, **_kwargs: object) -> None:
            return None

    repo = FakeRepo()
    monkeypatch.setattr(search_service, "search_title_page", fake_search_title_page)

    assert await search_once(cfg, repo, FakeLog()) == 3  # type: ignore[arg-type]
    assert calls == [(50, None), (50, "page-2"), (20, "page-3")]
    assert [upsert["youtube_id"] for upsert in repo.upserts] == [
        "youtube0001",
        "youtube0002",
        "youtube0003",
    ]
    telemetry = read_youtube_api_telemetry(cfg.paths.youtube_telemetry_path)
    assert telemetry["estimated_quota_units"] == 303
    assert telemetry["next_page_token"] == "page-4"
