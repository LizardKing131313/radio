from __future__ import annotations

import os
from functools import cache
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingConfigError(RuntimeError):
    """Raised on the first access to a critical config value when it is missing."""


class Paths(BaseModel):
    base: Path = Field(default=Path("/opt/radio"))
    data: Path = Field(default=Path("/opt/radio/data"))
    data_base: Path = Field(default=Path("/opt/radio/data/radio.sqlite"))
    cookies: Path = Field(default=Path("/opt/radio/data/cookies.txt"))
    cache_cold: Path = Field(default=Path("/opt/radio/cache/cold"))
    cache_hot: Path = Field(default=Path("/opt/radio/cache/hot"))
    runtime_fifo_dir: Path = Field(default=Path("/opt/radio/runtime/fifo"))
    runtime_info_dir: Path = Field(default=Path("/opt/radio/runtime/info"))
    fifo_audio_path: Path = Field(default=Path("/opt/radio/runtime/fifo/radio.wav"))
    nowplaying_path: Path = Field(default=Path("/opt/radio/runtime/info/nowplaying.txt"))
    www_hls_ts: Path = Field(default=Path("/opt/radio/www/hls/ts"))
    www_hls_mp4: Path = Field(default=Path("/opt/radio/www/hls/mp4"))
    www_html: Path = Field(default=Path("/opt/radio/www/html"))


class LiquidSoapSettings(BaseModel):

    telnet_host: str = Field(default="127.0.0.1")
    telnet_port: int = Field(default=1234)
    restart_timer_max_sec: int = Field(default=5)
    connect_timeout_sec: float = Field(default=5.0)
    command_timeout_sec: float = Field(default=5.0)
    per_line_timeout_sec: float = Field(default=0.2)
    max_lines: int = Field(default=1000)
    max_total_bytes: int = Field(default=256 * 1024)


class HLSSettings(BaseModel):
    """HLS knobs kept close to ffmpeg flags for easier mapping."""

    hls_time: int = Field(default=6)
    hls_list_size: int = Field(default=12)
    hls_delete_threshold: int = Field(default=14)
    bitrates: list[int] = Field(default_factory=lambda: [64, 96, 128])


class SearchSettings(BaseModel):

    title: str = Field(default="говновоз")
    interval_sec: int = Field(default=5)  # pause between ticks
    lru_capacity: int = Field(default=50_000)  # remember last N ids
    window_size: int = Field(default=200)  # results per search "window"
    max_windows_per_tick: int = Field(default=15)  # during full crawl
    early_stop_new: int = Field(default=20)  # stop tick after K new items (incremental)


class Secrets(BaseModel):
    """
    Holds secrets; values are optional at construction time and validated lazily on access.
    Filled from env explicitly in AppConfig.from_yaml().
    """

    youtube_api_key_raw: SecretStr | None = Field(default=None)
    youtube_stream_key_raw: SecretStr | None = Field(default=None)
    rtmp_enabled: bool = Field(default=False)
    rtmp_ingest_url: str = Field(default="rtmp://a.rtmp.youtube.com/live2")

    @property
    def youtube_api_key(self) -> SecretStr:
        if self.youtube_api_key_raw is None:
            raise MissingConfigError(
                "Missing YouTube API key. Set RADIO_YOUTUBE_API_KEY or YOUTUBE_API_KEY."
            )
        return self.youtube_api_key_raw

    @property
    def youtube_stream_key(self) -> SecretStr:
        if self.youtube_stream_key_raw is None:
            raise MissingConfigError(
                "Missing YouTube RTMP stream key. Set RADIO_YOUTUBE_STREAM_KEY / "
                "YT_STREAM_KEY or YOUTUBE_STREAM_KEY."
            )
        return self.youtube_stream_key_raw

    @property
    def youtube_stream_url(self) -> str:
        if not self.rtmp_enabled:
            raise MissingConfigError(
                "YouTube RTMP is disabled (RADIO_YOUTUBE_RTMP_ENABLED=false). "
                "Enable it to build stream URL."
            )
        key = self.youtube_stream_key  # lazy failure if missing
        return f"{self.rtmp_ingest_url.rstrip('/')}/{key.get_secret_value()}"


class AppConfig(BaseSettings):
    """
    Main application settings.

    Source of truth:
      1) YAML file (structured config)
      2) Env overrides for secrets (flat RADIO_* or plain fallbacks),
         merged explicitly in from_yaml().

    We do NOT parse HLS or bitrates from env to avoid flaky behavior.
    """

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_prefix="",  # no automatic prefixing
        env_nested_delimiter="__",  # reserved for future nested overrides
        extra="ignore",
        case_sensitive=False,
    )

    paths: Paths = Field(default_factory=Paths)
    liquidsoap: LiquidSoapSettings = Field(default_factory=LiquidSoapSettings)
    hls: HLSSettings = Field(default_factory=HLSSettings)
    search: SearchSettings = Field(default_factory=SearchSettings)
    secrets: Secrets = Field(default_factory=Secrets)

    # ---------- YAML loader with explicit env merge ----------
    @classmethod
    def from_yaml(cls, path: Path | None = None) -> AppConfig:
        """
        Load config from YAML, then overlay flat env secrets.
        Search order if path is not provided:
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

        # ---- explicit env merge (no pydantic alias magic) ----
        def _get_env(*names: str) -> str | None:
            for n in names:
                v = os.getenv(n)
                if v is not None and v != "":
                    return v
            return None

        # API key
        api_key = _get_env("RADIO_YOUTUBE_API_KEY", "YOUTUBE_API_KEY")
        if api_key is not None:
            cfg.secrets.youtube_api_key_raw = SecretStr(api_key)

        # Stream key (support multiple common names)
        stream_key = _get_env("RADIO_YOUTUBE_STREAM_KEY", "YT_STREAM_KEY", "YOUTUBE_STREAM_KEY")
        if stream_key is not None:
            cfg.secrets.youtube_stream_key_raw = SecretStr(stream_key)

        # RTMP enabled (truthy parser)
        enabled_raw = _get_env("RADIO_YOUTUBE_RTMP_ENABLED", "YOUTUBE_RTMP_ENABLED")
        if enabled_raw is not None:
            truthy = {"1", "true", "yes", "on"}
            cfg.secrets.rtmp_enabled = enabled_raw.strip().lower() in truthy

        # RTMP ingest URL
        ingest = _get_env("RADIO_YOUTUBE_RTMP_URL", "YOUTUBE_RTMP_URL")
        if ingest is not None:
            cfg.secrets.rtmp_ingest_url = ingest

        return cfg


@cache
def get_settings() -> AppConfig:
    # Read from YAML by default; callers can still pass a path to from_yaml() directly if needed.
    return AppConfig.from_yaml()


__all__ = [
    "AppConfig",
    "HLSSettings",
    "LiquidSoapSettings",
    "MissingConfigError",
    "Paths",
    "SearchSettings",
    "Secrets",
    "get_settings",
]
