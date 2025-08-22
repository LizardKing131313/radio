from __future__ import annotations

from pathlib import Path

import pytest

from manager.config import AppConfig, MissingConfigError


# ---- Env cleanup ----
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "RADIO_YOUTUBE_API_KEY",
        "YOUTUBE_API_KEY",
        "RADIO_YOUTUBE_STREAM_KEY",
        "YOUTUBE_STREAM_KEY",
        "YT_STREAM_KEY",
        "RADIO_YOUTUBE_RTMP_ENABLED",
        "YOUTUBE_RTMP_ENABLED",
        "RADIO_YOUTUBE_RTMP_URL",
        "YOUTUBE_RTMP_URL",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---- 1) YAML defaults load ----
def test_yaml_defaults(tmp_path: Path) -> None:
    cfg = AppConfig.from_yaml(
        _write_yaml(
            tmp_path / "config.yaml",
            """\
paths:
  base: /opt/radio
hls:
  hls_time: 6
  hls_list_size: 12
  hls_delete_threshold: 14
  bitrates: [64, 96, 128]
secrets: {}
""",
        )
    )
    assert cfg.paths.base == Path("/opt/radio")
    assert cfg.hls.hls_time == 6
    assert cfg.hls.hls_list_size == 12
    assert cfg.hls.hls_delete_threshold == 14
    assert cfg.hls.bitrates == [64, 96, 128]


# ---- 2) Bitrates via YAML only ----
def test_yaml_custom_bitrates(tmp_path: Path) -> None:
    cfg = AppConfig.from_yaml(
        _write_yaml(
            tmp_path / "config.yaml",
            "hls:\n  bitrates: [32, 64, 192]\n",
        )
    )
    assert cfg.hls.bitrates == [32, 64, 192]


# ---- 3) Lazy secret: API key missing raises on access ----
def test_missing_api_key_raises() -> None:
    cfg = AppConfig.from_yaml()  # no file → defaults
    with pytest.raises(MissingConfigError) as ei:
        _ = cfg.secrets.youtube_api_key
    assert "missing youtube api key" in str(ei.value).lower()


# ---- 4) RTMP enabled without stream key → raises about stream key ----
def test_rtmp_enabled_without_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADIO_YOUTUBE_RTMP_ENABLED", "true")
    cfg = AppConfig.from_yaml()
    with pytest.raises(MissingConfigError) as ei:
        _ = cfg.secrets.youtube_stream_url
    assert "stream key" in str(ei.value).lower()


# ---- 5) RTMP enabled with key → builds URL ----
def test_rtmp_enabled_with_key_builds_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RADIO_YOUTUBE_RTMP_ENABLED", "1")
    monkeypatch.setenv("RADIO_YOUTUBE_STREAM_KEY", "abc-123-xyz")
    monkeypatch.setenv("RADIO_YOUTUBE_RTMP_URL", "rtmp://b.rtmp.youtube.com/live2")
    cfg = AppConfig.from_yaml()
    assert cfg.secrets.youtube_stream_url == "rtmp://b.rtmp.youtube.com/live2/abc-123-xyz"
