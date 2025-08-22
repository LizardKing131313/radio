from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class MissingConfigError(RuntimeError):
    """Raised on the first access to a critical config value when it is missing."""


class Paths(BaseModel):
    """Default filesystem layout under /opt/radio."""

    base: Path = Path("/opt/radio")
    data: Path = Path("/opt/radio/data")
    cache_cold: Path = Path("/opt/radio/cache/cold")
    cache_hot: Path = Path("/opt/radio/cache/hot")
    runtime_fifo_dir: Path = Path("/opt/radio/runtime/fifo")
    runtime_info_dir: Path = Path("/opt/radio/runtime/info")
    fifo_audio_path: Path = Path("/opt/radio/runtime/fifo/radio.wav")
    nowplaying_path: Path = Path("/opt/radio/runtime/info/nowplaying.txt")
    www_hls_ts: Path = Path("/opt/radio/www/hls/ts")
    www_hls_mp4: Path = Path("/opt/radio/www/hls/mp4")
    www_html: Path = Path("/opt/radio/www/html")


class HLSSettings(BaseModel):
    """HLS knobs kept close to ffmpeg flags for easier mapping."""

    hls_time: int = 6
    hls_list_size: int = 12
    hls_delete_threshold: int = 14
    bitrates: list[int] = Field(default_factory=lambda: [64, 96, 128])


class Secrets(BaseModel):
    """
    Holds secrets; values are optional at construction time and validated lazily on access.
    Filled from env explicitly in AppConfig.from_yaml().
    """

    youtube_api_key_raw: SecretStr | None = None
    youtube_stream_key_raw: SecretStr | None = None
    rtmp_enabled: bool = False
    rtmp_ingest_url: str = "rtmp://a.rtmp.youtube.com/live2"

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
    hls: HLSSettings = Field(default_factory=HLSSettings)
    secrets: Secrets = Field(default_factory=Secrets)

    # Convenience proxies
    @property
    def fifo_audio_path(self) -> Path:
        return self.paths.fifo_audio_path

    @property
    def nowplaying_path(self) -> Path:
        return self.paths.nowplaying_path

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


__all__ = [
    "AppConfig",
    "HLSSettings",
    "MissingConfigError",
    "Paths",
    "Secrets",
]
