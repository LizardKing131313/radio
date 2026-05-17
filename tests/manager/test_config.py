from __future__ import annotations

from pathlib import Path

import pytest

from manager.config import AppConfig, MissingConfigError, get_settings


# ---- Чистим env перед каждым тестом ----
@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    keys = [
        "RADIO_YOUTUBE_API_KEY",
        "YOUTUBE_API_KEY",
        "RADIO_DATABASE_DSN",
        "DATABASE_URL",
        "POSTGRES_DSN",
        "RADIO_ADMIN_TOKEN",
        "ADMIN_TOKEN",
    ]
    for k in keys:
        monkeypatch.delenv(k, raising=False)


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# ---- YAML загружает дефолты ----
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
    assert cfg.paths.youtube_telemetry_path == Path("/opt/radio/runtime/info/youtube_api.json")
    assert cfg.hls.hls_time == 6
    assert cfg.hls.hls_list_size == 12
    assert cfg.hls.hls_delete_threshold == 14
    assert cfg.hls.bitrates == [64, 96, 128]
    assert cfg.search.interval_sec == 3600
    assert cfg.search.window_size == 25
    assert cfg.search.max_windows_per_tick == 1
    assert cfg.search.quota_backoff_sec == 21600


# ---- Bitrates задаются только через YAML ----
def test_yaml_custom_bitrates(tmp_path: Path) -> None:
    cfg = AppConfig.from_yaml(
        _write_yaml(
            tmp_path / "config.yaml",
            "hls:\n  bitrates: [32, 64, 192]\n",
        )
    )
    assert cfg.hls.bitrates == [32, 64, 192]


def test_yaml_root_must_be_mapping(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must define a mapping"):
        AppConfig.from_yaml(_write_yaml(tmp_path / "config.yaml", "- bad\n- root\n"))


# ---- Секреты валидируются лениво при доступе ----
def test_missing_api_key_raises() -> None:
    cfg = AppConfig.from_yaml()  # файла нет -> дефолты
    with pytest.raises(MissingConfigError) as ei:
        _ = cfg.secrets.youtube_api_key
    assert "missing youtube api key" in str(ei.value).lower()


def test_api_key_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTUBE_API_KEY", "api-key")
    cfg = AppConfig.from_yaml()
    assert cfg.secrets.youtube_api_key.get_secret_value() == "api-key"


def test_admin_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "admin-token")
    cfg = AppConfig.from_yaml()
    assert cfg.secrets.admin_token.get_secret_value() == "admin-token"


def test_database_dsn_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://radio:secret@localhost/radio")
    cfg = AppConfig.from_yaml()
    assert cfg.database.dsn.get_secret_value() == "postgresql://radio:secret@localhost/radio"


def test_missing_database_dsn_raises() -> None:
    cfg = AppConfig.from_yaml()
    with pytest.raises(MissingConfigError) as ei:
        _ = cfg.database.dsn
    assert "postgresql dsn" in str(ei.value).lower()


def test_get_settings_returns_cached_config() -> None:
    get_settings.cache_clear()
    first = get_settings()
    second = get_settings()
    assert first is second
    get_settings.cache_clear()
