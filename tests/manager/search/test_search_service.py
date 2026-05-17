from __future__ import annotations

from manager.config import AppConfig
from manager.search.search_helpers import YouTubeAPIError
from manager.search.search_service import _next_sleep_sec


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
