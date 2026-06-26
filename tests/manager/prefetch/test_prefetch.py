from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from pydantic import SecretStr

from manager.config import AppConfig
from manager.prefetch.prefetch import PrefetchWorker
from manager.track_queue.models import Track
from manager.track_queue.orm import Base


@pytest.fixture
def worker(tmp_path: Path) -> Iterator[PrefetchWorker]:
    cfg = AppConfig()
    cfg.database.dsn_raw = SecretStr(f"sqlite+pysqlite:///{tmp_path / 'prefetch.db'}")
    cfg.paths.cache_cold = tmp_path / "cold"
    cfg.paths.cache_hot = tmp_path / "hot"
    cfg.paths.cache_blacklist = tmp_path / "blacklist" / "state.json"
    cfg.prefetch.hot_max_items = 2

    prefetch = PrefetchWorker(config=cfg)
    Base.metadata.create_all(prefetch.database.engine)
    prefetch._ensure_dirs()
    try:
        yield prefetch
    finally:
        prefetch.database.close()


@pytest.mark.asyncio
async def test_hot_cache_moves_files_without_cold_duplicates(
    worker: PrefetchWorker,
) -> None:
    track_ids = {
        youtube_id: worker.tracks.upsert(youtube_id, f"Track {youtube_id}", 120)
        for youtube_id in ("track_a", "track_b", "track_c", "track_d")
    }
    for index, youtube_id in enumerate(("track_a", "track_b", "track_c"), start=1):
        path = _write_audio(worker.config.paths.cache_cold / f"{youtube_id}.opus", index)
        worker.tracks.update_track_audio(
            track_id=track_ids[youtube_id],
            audio_path=str(path),
        )

    await worker._refresh_hot_cache()

    assert _names(worker.config.paths.cache_hot) == {"track_b.opus", "track_c.opus"}
    assert _names(worker.config.paths.cache_cold) == {"track_a.opus"}
    assert _names(worker.config.paths.cache_hot).isdisjoint(_names(worker.config.paths.cache_cold))
    assert worker.tracks.get(track_ids["track_b"]).cache_state == "hot"
    assert "/hot/" in worker.tracks.get(track_ids["track_b"]).audio_path.replace("\\", "/")
    assert worker.tracks.get(track_ids["track_a"]).cache_state == "cold"

    hot_b = worker.config.paths.cache_hot / "track_b.opus"
    hot_c = worker.config.paths.cache_hot / "track_c.opus"
    os.utime(hot_c, (10, 10))
    os.utime(hot_b, (20, 20))
    cold_d = _write_audio(worker.config.paths.cache_cold / "track_d.opus", 30)
    worker.tracks.update_track_audio(track_id=track_ids["track_d"], audio_path=str(cold_d))

    hot_d = await worker._promote_to_hot(cold_d)
    worker.tracks.update_track_cached(
        track_id=track_ids["track_d"],
        cache_state="hot",
        audio_path=str(hot_d),
    )

    assert _names(worker.config.paths.cache_hot) == {"track_b.opus", "track_d.opus"}
    assert _names(worker.config.paths.cache_cold) == {"track_a.opus", "track_c.opus"}
    assert _names(worker.config.paths.cache_hot).isdisjoint(_names(worker.config.paths.cache_cold))
    assert worker.tracks.get(track_ids["track_c"]).cache_state == "cold"
    assert "/cold/" in worker.tracks.get(track_ids["track_c"]).audio_path.replace("\\", "/")
    assert worker.tracks.get(track_ids["track_d"]).cache_state == "hot"

    duplicate_cold_b = _write_audio(worker.config.paths.cache_cold / "track_b.opus", 40)
    worker.tracks.update_track_audio(
        track_id=track_ids["track_b"],
        audio_path=str(duplicate_cold_b),
    )

    await worker._refresh_hot_cache()

    assert not duplicate_cold_b.exists()
    assert worker.tracks.get(track_ids["track_b"]).cache_state == "hot"
    assert "/hot/" in worker.tracks.get(track_ids["track_b"]).audio_path.replace("\\", "/")
    assert _names(worker.config.paths.cache_hot).isdisjoint(_names(worker.config.paths.cache_cold))


@pytest.mark.asyncio
async def test_process_track_uses_existing_hot_file(worker: PrefetchWorker) -> None:
    track_id = worker.tracks.upsert("track_hot", "Hot Track", 120)
    hot_path = _write_audio(worker.config.paths.cache_hot / "track_hot.opus", 1)

    await worker._process_track(
        Track(
            id=track_id,
            youtube_id="track_hot",
            title="Hot Track",
            duration_sec=120,
            url="https://youtu.be/track_hot",
        )
    )

    track = worker.tracks.get(track_id)
    assert track.cache_state == "hot"
    assert track.audio_path == str(hot_path)
    assert not (worker.config.paths.cache_cold / "track_hot.opus").exists()


@pytest.mark.asyncio
async def test_download_uses_staging_outside_liquidsoap_playlists(
    worker: PrefetchWorker,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    track_id = worker.tracks.upsert("track_new", "New Track", 120)

    async def fake_download(track: Track, out_path: Path) -> bool:
        assert track.youtube_id == "track_new"
        assert out_path.parent == worker._staging_dir()
        _write_audio(out_path, 1)
        (out_path.parent / f"{track.youtube_id}.opus.tmp").write_text(
            "partial",
            encoding="utf-8",
        )
        return True

    async def fake_measure_lufs(path: Path) -> float:
        assert path.parent == worker._staging_dir()
        return -12.5

    monkeypatch.setattr(worker, "_download_opus", fake_download)
    monkeypatch.setattr(worker, "_measure_lufs", fake_measure_lufs)

    await worker._process_track(
        Track(
            id=track_id,
            youtube_id="track_new",
            title="New Track",
            duration_sec=120,
            url="https://youtu.be/track_new",
        )
    )

    track = worker.tracks.get(track_id)
    assert track.cache_state == "hot"
    assert track.loudness_lufs == -12.5
    assert track.audio_path == str(worker.config.paths.cache_hot / "track_new.opus")
    assert _names(worker.config.paths.cache_hot) == {"track_new.opus"}
    assert _names(worker.config.paths.cache_cold) == set()
    assert _tmp_names(worker.config.paths.cache_hot) == set()
    assert _tmp_names(worker.config.paths.cache_cold) == set()
    assert _tmp_names(worker._staging_dir()) == {"track_new.opus.tmp"}

    await worker._cleanup_staging_cache()

    assert _tmp_names(worker._staging_dir()) == set()


def _write_audio(path: Path, mtime: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("audio", encoding="utf-8")
    os.utime(path, (mtime, mtime))
    return path


def _names(path: Path) -> set[str]:
    return {item.name for item in path.glob("*.opus")}


def _tmp_names(path: Path) -> set[str]:
    return {item.name for item in path.glob("*.tmp")}
