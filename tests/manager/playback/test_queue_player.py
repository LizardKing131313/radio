from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from manager.config import AppConfig
from manager.playback.queue_player import QueueMetadata, QueuePlayer, read_queue_metadata
from manager.playback.telnet import LiquidsoapTelnetError
from manager.track_queue.db import Database
from manager.track_queue.orm import Base
from manager.track_queue.repo import QueueRepo, TracksRepo


class FakeLiquidsoap:
    def __init__(self, queue_body: str = "3") -> None:
        self.pushed: list[str] = []
        self.queue_body = queue_body

    def push_request(self, uri: str) -> str:
        self.pushed.append(uri)
        return "OK"

    def queue_requests(self) -> str:
        return self.queue_body


class FailingLiquidsoap(FakeLiquidsoap):
    def push_request(self, uri: str) -> str:
        self.pushed.append(uri)
        raise LiquidsoapTelnetError("down")


@pytest.fixture
def runtime(tmp_path: Path) -> Iterator[tuple[AppConfig, Database]]:
    cfg = AppConfig()
    cfg.paths.nowplaying_path = tmp_path / "nowplaying.txt"
    db = Database(app_config=cfg, dsn=f"sqlite+pysqlite:///{tmp_path / 'queue.db'}")
    Base.metadata.create_all(db.engine)
    yield cfg, db
    db.close()


def test_queue_player_push_start_and_finish(
    runtime: tuple[AppConfig, Database], tmp_path: Path
) -> None:
    cfg, db = runtime
    audio = tmp_path / "track.opus"
    audio.write_text("audio", encoding="utf-8")
    tracks = TracksRepo(db)
    track_id = tracks.upsert("youtube0001", "Track", 120, audio_path=str(audio))
    queue_id = QueueRepo(db).enqueue(track_id)
    liquidsoap = FakeLiquidsoap()
    player = QueuePlayer(config=cfg, database=db, liquidsoap=liquidsoap)

    player.tick()
    assert len(liquidsoap.pushed) == 1
    assert f'queue_id="{queue_id}"' in liquidsoap.pushed[0]
    assert f'track_id="{track_id}"' in liquidsoap.pushed[0]
    active = QueueRepo(db).current_active()
    assert active is not None
    assert active[0].status == "queued"

    cfg.paths.nowplaying_path.with_name("nowplaying.txt.kv").write_text(
        f"queue_id={queue_id}\ntrack_id={track_id}\n",
        encoding="utf-8",
    )
    player.tick()
    current = QueueRepo(db).current_playing()
    assert current is not None
    assert current[0].id == queue_id
    assert TracksRepo(db).get(track_id).play_count == 1

    player._finish_old_playing(QueueMetadata(queue_id=queue_id, track_id=track_id))
    player._mark_started(QueueMetadata(queue_id=queue_id, track_id=track_id))
    assert QueueRepo(db).current_playing() is not None

    cfg.paths.nowplaying_path.with_name("nowplaying.txt.kv").write_text(
        "title=library\nqueue_id=\ntrack_id=\n",
        encoding="utf-8",
    )
    player.tick()
    assert QueueRepo(db).history(limit=1)[0][0].status == "done"
    player.close()


def test_queue_player_skips_missing_audio(runtime: tuple[AppConfig, Database]) -> None:
    cfg, db = runtime
    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120)
    queue_id = QueueRepo(db).enqueue(track_id)

    QueuePlayer(config=cfg, database=db, liquidsoap=FakeLiquidsoap()).tick()

    history = QueueRepo(db).history(limit=1)
    assert history[0][0].id == queue_id
    assert history[0][0].status == "skipped"


def test_queue_player_releases_item_when_liquidsoap_fails(
    runtime: tuple[AppConfig, Database], tmp_path: Path
) -> None:
    cfg, db = runtime
    audio = tmp_path / "track.opus"
    audio.write_text("audio", encoding="utf-8")
    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120, audio_path=str(audio))
    QueueRepo(db).enqueue(track_id)
    player = QueuePlayer(config=cfg, database=db, liquidsoap=FailingLiquidsoap())

    with pytest.raises(LiquidsoapTelnetError):
        player.tick()

    assert QueueRepo(db).peek_next() is not None


def test_queue_player_ignores_unmatched_metadata(runtime: tuple[AppConfig, Database]) -> None:
    cfg, db = runtime
    player = QueuePlayer(config=cfg, database=db, liquidsoap=FakeLiquidsoap())
    player._mark_started(QueueMetadata(queue_id=1, track_id=1))

    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(db)
    queue_id = queue.enqueue(track_id)
    queue.reserve_next()

    player._mark_started(QueueMetadata(queue_id=queue_id + 100, track_id=999))

    assert queue.current_playing() is None
    assert queue.current_active() is not None


def test_queue_player_repairs_lost_queued_item(
    runtime: tuple[AppConfig, Database], tmp_path: Path
) -> None:
    cfg, db = runtime
    audio = tmp_path / "track.opus"
    audio.write_text("audio", encoding="utf-8")
    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120, audio_path=str(audio))
    queue = QueueRepo(db)
    queue_id = queue.enqueue(track_id)
    queue.reserve_next()
    liquidsoap = FakeLiquidsoap(queue_body="")

    QueuePlayer(config=cfg, database=db, liquidsoap=liquidsoap).tick()

    active = queue.current_active()
    assert active is not None
    assert active[0].id == queue_id
    assert active[0].status == "queued"
    assert len(liquidsoap.pushed) == 1


def test_queue_player_keeps_live_queued_item(runtime: tuple[AppConfig, Database]) -> None:
    cfg, db = runtime
    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(db)
    queue_id = queue.enqueue(track_id)
    queue.reserve_next()

    QueuePlayer(config=cfg, database=db, liquidsoap=FakeLiquidsoap(queue_body="3")).tick()

    active = queue.current_active()
    assert active is not None
    assert active[0].id == queue_id
    assert active[0].status == "queued"


def test_queue_player_does_not_release_playing_item(runtime: tuple[AppConfig, Database]) -> None:
    cfg, db = runtime
    track_id = TracksRepo(db).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(db)
    queue_id = queue.enqueue(track_id)
    queue.mark_playing(queue_id)
    player = QueuePlayer(config=cfg, database=db, liquidsoap=FakeLiquidsoap(queue_body=""))

    player._release_lost_queued(QueueMetadata(queue_id=None, track_id=None))

    assert queue.current_playing() is not None


def test_read_queue_metadata_paths(tmp_path: Path) -> None:
    nowplaying = tmp_path / "nowplaying.txt"
    assert read_queue_metadata(nowplaying) == QueueMetadata(queue_id=None, track_id=None)

    nowplaying.with_name("nowplaying.txt.kv").write_text(
        "bad-line\nqueue_id=bad\ntrack_id=42\n",
        encoding="utf-8",
    )
    assert read_queue_metadata(nowplaying) == QueueMetadata(queue_id=None, track_id=42)
