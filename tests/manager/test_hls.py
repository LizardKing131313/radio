from __future__ import annotations

from pathlib import Path

import pytest

from manager import hls
from manager.config import AppConfig, HLSSettings, Paths


def _config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        paths=Paths(
            fifo_audio_path=tmp_path / "runtime" / "fifo" / "radio.wav",
            www_hls_ts=tmp_path / "www" / "hls" / "ts",
            www_hls_mp4=tmp_path / "www" / "hls" / "mp4",
        ),
        hls=HLSSettings(
            hls_time=4,
            hls_list_size=3,
            hls_delete_threshold=5,
            bitrates=[64, 128],
        ),
    )


def test_build_ffmpeg_hls_args(tmp_path: Path) -> None:
    cfg = _config(tmp_path)

    args = hls.build_ffmpeg_hls_args(cfg)

    assert args[:7] == [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(cfg.paths.fifo_audio_path),
        "-map",
    ]
    assert args.count("-f") == 2
    assert args.count("hls") == 2
    assert args.count("-map") == 4
    assert "a:0,name:64k a:1,name:128k" in args
    assert str(cfg.paths.www_hls_ts / "v%v" / "seg_%05d.ts") in args
    assert str(cfg.paths.www_hls_mp4 / "v%v" / "seg_%05d.m4s") in args


def test_exec_ffmpeg_hls_with_explicit_config(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    cfg = _config(tmp_path)
    captured: dict[str, list[str]] = {}

    def fake_execvp(program: str, args: list[str]) -> None:
        captured["args"] = [program, *args]

    monkeypatch.setattr(hls.os, "execvp", fake_execvp)

    assert hls.exec_ffmpeg_hls(cfg) == 1
    assert captured["args"][0] == "ffmpeg"
    assert (cfg.paths.www_hls_ts / "v64k").is_dir()
    assert (cfg.paths.www_hls_mp4 / "v128k").is_dir()


def test_exec_ffmpeg_hls_uses_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg = _config(tmp_path)
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr(hls, "get_settings", lambda: cfg)
    monkeypatch.setattr(
        hls.os,
        "execvp",
        lambda program, args: captured.setdefault("args", [program, *args]),
    )

    assert hls.exec_ffmpeg_hls() == 1
    assert captured["args"][0] == "ffmpeg"
