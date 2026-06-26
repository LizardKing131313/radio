from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from manager import now_playing as now_playing_module
from manager.config import AppConfig, HLSSettings, Paths
from manager.now_playing import current_snapshot


def test_current_snapshot_empty_source(tmp_path: Path) -> None:
    config = AppConfig(paths=Paths(nowplaying_path=tmp_path / "nowplaying.txt"))

    snapshot = current_snapshot(config, now=datetime(2026, 1, 1, tzinfo=UTC))

    assert snapshot == {
        "source": None,
        "hls": {
            "live_offset_sec": 6,
            "age_sec": None,
            "estimated_audible_at": None,
            "is_probably_audible": False,
        },
    }


def test_current_snapshot_reads_liquidsoap_files_and_hls_offset(tmp_path: Path) -> None:
    nowplaying = tmp_path / "nowplaying.txt"
    nowplaying.write_text("Artist - Title\n", encoding="utf-8")
    nowplaying.with_name(nowplaying.name + ".kv").write_text(
        "title=Title\nartist=Artist\nalbum=Album\n",
        encoding="utf-8",
    )
    config = AppConfig(
        paths=Paths(nowplaying_path=nowplaying),
        hls=HLSSettings(hls_time=6, hls_list_size=2),
    )

    snapshot = current_snapshot(config, now=datetime(2200, 1, 1, tzinfo=UTC))
    source = cast(dict[str, object], snapshot["source"])
    hls = cast(dict[str, object], snapshot["hls"])

    assert source["title"] == "Title"
    assert source["artist"] == "Artist"
    assert source["album"] == "Album"
    assert source["line"] == "Artist - Title"
    assert hls["live_offset_sec"] == 12
    assert hls["is_probably_audible"] is True
    assert isinstance(hls["age_sec"], int)
    assert isinstance(hls["estimated_audible_at"], str)


def test_current_snapshot_plain_file_before_hls_offset(tmp_path: Path) -> None:
    nowplaying = tmp_path / "nowplaying.txt"
    nowplaying.write_text("Raw Line\n", encoding="utf-8")
    config = AppConfig(
        paths=Paths(nowplaying_path=nowplaying),
        hls=HLSSettings(hls_time=1, hls_list_size=12),
    )

    snapshot = current_snapshot(config, now=datetime.fromtimestamp(nowplaying.stat().st_mtime, UTC))
    source = cast(dict[str, object], snapshot["source"])
    hls = cast(dict[str, object], snapshot["hls"])

    assert source["title"] is None
    assert source["line"] == "Raw Line"
    assert hls["live_offset_sec"] == 3
    assert hls["age_sec"] == 0
    assert hls["is_probably_audible"] is False


def test_current_snapshot_uses_current_time_when_mtime_disappears(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    nowplaying = tmp_path / "nowplaying.txt"
    nowplaying.write_text("Raw Line\n", encoding="utf-8")
    nowplaying.with_name(nowplaying.name + ".kv").write_text("broken\n=bad\n", encoding="utf-8")
    monkeypatch.setattr(now_playing_module, "_mtime", lambda _path: None)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    config = AppConfig(paths=Paths(nowplaying_path=nowplaying))

    snapshot = current_snapshot(config, now=now)
    source = cast(dict[str, object], snapshot["source"])

    assert source["updated_at"] == now.isoformat()
    assert source["line"] == "Raw Line"
