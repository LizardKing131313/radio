from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingConfigError(RuntimeError):
    """Ошибка ленивой проверки: критичный параметр запросили, но его нет."""


class Paths(BaseModel):
    base: Path = Field(default=Path("/opt/radio"))
    data: Path = Field(default=Path("/opt/radio/data"))
    cookies: Path = Field(default=Path("/opt/radio/data/cookies.txt"))
    cache_cold: Path = Field(default=Path("/opt/radio/cache/cold"))
    cache_hot: Path = Field(default=Path("/opt/radio/cache/hot"))
    cache_blacklist: Path = Field(default=Path("/opt/radio/cache/blacklist"))
    runtime_fifo_dir: Path = Field(default=Path("/opt/radio/runtime/fifo"))
    runtime_info_dir: Path = Field(default=Path("/opt/radio/runtime/info"))
    fifo_audio_path: Path = Field(default=Path("/opt/radio/runtime/fifo/radio.wav"))
    nowplaying_path: Path = Field(default=Path("/opt/radio/runtime/info/nowplaying.txt"))
    youtube_telemetry_path: Path = Field(default=Path("/opt/radio/runtime/info/youtube_api.json"))
    www_hls_ts: Path = Field(default=Path("/opt/radio/www/hls/ts"))
    www_hls_mp4: Path = Field(default=Path("/opt/radio/www/hls/mp4"))
    www_html: Path = Field(default=Path("/opt/radio/www/html"))


class HLSSettings(BaseModel):
    """Настройки HLS названы почти как ffmpeg-флаги, чтобы проще сверять CLI."""

    hls_time: int = Field(default=6)
    hls_list_size: int = Field(default=12)
    hls_delete_threshold: int = Field(default=14)
    bitrates: list[int] = Field(default_factory=lambda: [64, 96, 128])


class SearchSettings(BaseModel):
    title: str = Field(default="говновоз")
    interval_sec: int = Field(default=21600)
    window_size: int = Field(default=10)
    max_windows_per_tick: int = Field(default=1)
    quota_backoff_sec: int = Field(default=43200)


class PrefetchSetting(BaseModel):
    interval_sec: int = Field(default=5)
    cold_quota_bytes: int = Field(default=5368709120)
    hot_max_items: int = Field(default=5)
    batch_size: int = Field(default=100)
    download_timeout_sec: int = Field(default=600)
    concurrent_downloads: int = Field(default=4)


class DatabaseSettings(BaseModel):
    """
    Настройки подключения к PostgreSQL.

    DDL принадлежит Alembic. Приложение только проверяет, что миграции уже
    применены, и после этого выполняет запросы репозиториев.
    """

    dsn_raw: SecretStr | None = Field(default=None)
    connect_timeout_sec: int = Field(default=5)
    application_name: str = Field(default="radio-manager")

    @property
    def dsn(self) -> SecretStr:
        if self.dsn_raw is None:
            raise MissingConfigError(
                "Missing PostgreSQL DSN. Set RADIO_DATABASE_DSN or DATABASE_URL."
            )
        return self.dsn_raw


class Secrets(BaseModel):
    """
    Секреты заполняются из env поверх YAML.

    Поля опциональны при создании конфига, а падают только при первом реальном
    доступе. Так тесты и команды без YouTube API key не ломаются на импорте.
    """

    youtube_api_key_raw: SecretStr | None = Field(default=None)
    admin_token_raw: SecretStr | None = Field(default=None)

    @property
    def youtube_api_key(self) -> SecretStr:
        if self.youtube_api_key_raw is None:
            raise MissingConfigError(
                "Missing YouTube API key. Set RADIO_YOUTUBE_API_KEY or YOUTUBE_API_KEY."
            )
        return self.youtube_api_key_raw

    @property
    def admin_token(self) -> SecretStr:
        if self.admin_token_raw is None:
            raise MissingConfigError("Missing admin token. Set RADIO_ADMIN_TOKEN or ADMIN_TOKEN.")
        return self.admin_token_raw


class AppConfig(BaseSettings):
    """
    Главный слой настроек приложения.

    Источники:
      1) YAML-файл для структурного runtime config.
      2) Env-переменные для секретов и DSN.

    HLS и bitrates не читаются из env, чтобы не плодить скрытые override-ы.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="",  # автоматический env binding выключен
        env_nested_delimiter="__",  # оставлено только как резерв для будущего
        extra="ignore",
        case_sensitive=False,
    )

    paths: Paths = Field(default_factory=Paths)
    hls: HLSSettings = Field(default_factory=HLSSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    prefetch: PrefetchSetting = Field(default_factory=PrefetchSetting)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    secrets: Secrets = Field(default_factory=Secrets)

    # YAML грузим явно, затем вручную накладываем env-секреты.
    @classmethod
    def from_yaml(cls, path: Path | None = None) -> AppConfig:
        """
        Загрузить YAML и поверх него наложить env.

        Порядок поиска, если путь не передан:
          ./data/config.yaml
          /opt/radio/data/config.yaml
        """
        candidates: list[Path] = []
        if path is not None:
            candidates.append(path)
        else:
            candidates.extend([Path("data/config.yaml"), Path("/opt/radio/data/config.yaml")])

        raw: dict[str, object] = {}
        for p in candidates:
            if p.exists():
                text = p.read_text(encoding="utf-8")
                loaded = yaml.safe_load(text) or {}
                if not isinstance(loaded, dict):
                    raise ValueError(f"YAML at {p} must define a mapping at the root")
                raw = loaded
                break

        cfg = cls.model_validate(raw)

        # Никакой магии alias-ов: видимые имена env явно перечислены здесь.
        def _get_env(*names: str) -> str | None:
            for n in names:
                v = os.getenv(n)
                if v is not None and v != "":
                    return v
            return None

        # Ключ нужен только search-воркеру, поэтому валидируется лениво.
        api_key = _get_env("RADIO_YOUTUBE_API_KEY", "YOUTUBE_API_KEY")
        if api_key is not None:
            cfg.secrets.youtube_api_key_raw = SecretStr(api_key)

        admin_token = _get_env("RADIO_ADMIN_TOKEN", "ADMIN_TOKEN")
        if admin_token is not None:
            cfg.secrets.admin_token_raw = SecretStr(admin_token)

        database_dsn = _get_env("RADIO_DATABASE_DSN", "DATABASE_URL", "POSTGRES_DSN")
        if database_dsn is not None:
            cfg.database.dsn_raw = SecretStr(database_dsn)

        return cfg


@cache
def get_settings() -> AppConfig:
    # Обычный runtime читает дефолтный YAML; тесты могут вызывать from_yaml(path).
    return AppConfig.from_yaml()


__all__ = [
    "AppConfig",
    "DatabaseSettings",
    "HLSSettings",
    "MissingConfigError",
    "Paths",
    "PrefetchSetting",
    "SearchSettings",
    "Secrets",
    "get_settings",
]
