from __future__ import annotations

import time
from pathlib import Path

import pytest

from manager.config import AppConfig, Paths
from manager.health import (
    check_component,
    heartbeat_path,
    is_fresh,
    newest_mtime,
    write_heartbeat,
)


def test_heartbeat_write_and_age(tmp_path: Path) -> None:
    path = tmp_path / "health" / "worker.json"
    write_heartbeat(path)
    now = path.stat().st_mtime
    assert path.exists()
    assert is_fresh(path, 10, now=now)
    assert not is_fresh(path, 10, now=now + 11)
    assert not is_fresh(tmp_path / "missing", 10, now=now)
    assert newest_mtime(tmp_path / "missing-root", "index.m3u8") is None


def test_component_checks_cover_workers_and_outputs(tmp_path: Path) -> None:
    runtime = tmp_path / "runtime" / "info"
    hls = tmp_path / "hls" / "ts" / "v128k"
    hls.mkdir(parents=True)
    nowplaying = runtime / "nowplaying.txt"
    nowplaying.parent.mkdir(parents=True)
    nowplaying.write_text("Track\n", encoding="utf-8")
    nowplaying.with_suffix(".txt.kv").write_text("title=Track\n", encoding="utf-8")
    playlist = hls / "index.m3u8"
    playlist.write_text("#EXTM3U\n", encoding="utf-8")
    config = AppConfig(
        paths=Paths(
            runtime_info_dir=runtime, nowplaying_path=nowplaying, www_hls_ts=tmp_path / "hls"
        )
    )
    for name in ("search", "prefetch", "queue-player"):
        write_heartbeat(heartbeat_path(config, name))
        assert check_component(config, name, 10, now=time.time() + 1)
    assert check_component(
        config, "liquidsoap", 10, now=nowplaying.with_suffix(".txt.kv").stat().st_mtime + 1
    )
    assert check_component(config, "ffmpeg", 10, now=playlist.stat().st_mtime + 1)


def test_component_checks_reject_stale_and_unknown(tmp_path: Path) -> None:
    config = AppConfig(paths=Paths(runtime_info_dir=tmp_path / "runtime"))
    with pytest.raises(ValueError, match="unknown health component"):
        check_component(config, "unknown", 10)
    assert not check_component(config, "search", 10)
