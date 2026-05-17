from __future__ import annotations

from collections.abc import Iterator

import pytest

from manager.config import AppConfig
from manager.track_queue.db import Database
from manager.track_queue.orm import Base, ConfigRow, _text
from manager.track_queue.repo import OffersRepo, QueueRepo, TracksRepo


@pytest.fixture
def database() -> Iterator[Database]:
    db = Database(app_config=AppConfig(), dsn="sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(db.engine)
    yield db
    db.close()


def _tracks(database: Database) -> TracksRepo:
    return TracksRepo(database)


def _queue(database: Database) -> QueueRepo:
    return QueueRepo(database)


def _offers(database: Database) -> OffersRepo:
    return OffersRepo(database)


def test_tracks_upsert_getters_and_updates(database: Database) -> None:
    tracks = _tracks(database)

    track_id = tracks.upsert("youtube0001", "Title", 61, channel="Channel")
    assert track_id == tracks.get_id_by_youtube_id("youtube0001")
    assert tracks.get(track_id).title == "Title"

    tracks.update_track_audio(track_id=track_id, audio_path="/tmp/a.opus", loudness_lufs=-14.0)
    same_id = tracks.upsert("youtube0001", "New Title", 62, audio_path=None)
    updated = tracks.get(same_id)
    assert updated.title == "New Title"
    assert updated.audio_path == "/tmp/a.opus"
    assert updated.loudness_lufs == -14.0

    tracks.touch_play(track_id)
    tracks.update_cache_state(
        track_id=track_id,
        cache_state="hot",
        cache_hot_until="2026-01-01T00:00:00+00:00",
        last_prefetch_at="2026-01-01T00:00:01+00:00",
    )
    tracks.update_cache_state(youtube_id="youtube0001", fail_count=3)
    tracks.update_cache_state(track_id=track_id)
    tracks.increment_fail_count(track_id)
    tracks.update_track_audio(youtube_id="youtube0001", audio_path="/tmp/b.opus")
    tracks.update_track_cached(
        track_id=track_id,
        cache_state="cold",
        cache_hot_until="2026-01-01T00:00:02Z",
    )
    tracks.update_track_cached(youtube_id="youtube0001", cache_state="hot")
    assert tracks.get(track_id).cache_state == "hot"

    with pytest.raises(KeyError):
        tracks.get_id_by_youtube_id("missing")
    with pytest.raises(KeyError):
        tracks.get(404)
    with pytest.raises(ValueError, match="required"):
        tracks.update_cache_state(cache_state="hot")


def test_tracks_missing_audio_filter(database: Database) -> None:
    tracks = _tracks(database)
    missing_id = tracks.upsert("missing0001", "Missing", 120)
    with_audio_id = tracks.upsert("cached00001", "Cached", 120, audio_path="/tmp/a.opus")
    inactive_id = tracks.upsert("inactive001", "Inactive", 120, is_active=0)

    assert [track.id for track in tracks.get_missing_audio(10)] == [missing_id]
    assert tracks.get(with_audio_id).audio_path == "/tmp/a.opus"
    assert tracks.get(inactive_id).is_active == 0


def test_tracks_list_stats_ban_restore_and_retry(database: Database) -> None:
    tracks = _tracks(database)
    ready_id = tracks.upsert("ready000001", "Ready Track", 120, channel="Chan")
    missing_id = tracks.upsert("missing0001", "Missing Track", 120)
    failed_id = tracks.upsert("failed00001", "Failed Track", 120)

    tracks.update_track_audio(track_id=ready_id, audio_path="/tmp/ready.opus")
    tracks.increment_fail_count(failed_id)

    assert [track.id for track in tracks.list_tracks(query="ready", status="downloaded")] == [
        ready_id
    ]
    assert [track.id for track in tracks.list_tracks(query="chan", status="downloaded")] == [
        ready_id
    ]
    assert [track.id for track in tracks.list_tracks(query="failed00001", status="failed")] == [
        failed_id
    ]
    assert [track.id for track in tracks.list_tracks(status="missing")] == [missing_id]
    assert len(tracks.list_tracks(status="all")) == 3
    assert tracks.stats()["downloaded"] == 1
    assert tracks.stats()["failed"] == 1

    banned = tracks.ban(ready_id)
    assert banned.is_active == 0
    assert banned.deleted_at is not None
    # Повторный поиск не должен вернуть забаненный трек обратно в активные.
    tracks.upsert("ready000001", "Ready Again", 120)
    assert tracks.get(ready_id).is_active == 0

    restored = tracks.restore(ready_id)
    assert restored.is_active == 1
    assert restored.deleted_at is None

    retry = tracks.retry_download(ready_id)
    assert retry.audio_path is None
    assert retry.cache_state == "none"
    assert retry.fail_count == 0

    with pytest.raises(ValueError, match="unknown track status"):
        tracks.list_tracks(status="broken")
    with pytest.raises(KeyError):
        tracks.ban(404)
    with pytest.raises(KeyError):
        tracks.restore(404)
    with pytest.raises(KeyError):
        tracks.retry_download(404)


def test_queue_insert_sort_read_and_cleanup(database: Database) -> None:
    tracks = _tracks(database)
    queue = _queue(database)
    first_track = tracks.upsert("youtube0001", "First", 120)
    second_track = tracks.upsert("youtube0002", "Second", 120)

    first_queue = queue.enqueue(first_track, sort_key=100.0)
    queue.mark_playing(first_queue)
    next_queue = queue.enqueue_next(second_track)
    after_current = queue.enqueue_after_current(second_track)

    current = queue.current_playing()
    assert current is not None
    assert current[0].id == first_queue
    assert current[1].id == first_track
    assert queue.peek_next() is not None
    assert queue.current_active() is not None
    assert [item.id for item, _track in queue.list_visible()] == [
        first_queue,
        after_current,
        next_queue,
    ]

    queue.mark_done(first_queue)
    queue.mark_done(next_queue, skipped=True)
    assert queue.history(limit=2)
    assert queue.cleanup_done(keep=1) == 1


def test_queue_empty_paths(database: Database) -> None:
    tracks = _tracks(database)
    queue = _queue(database)
    track_id = tracks.upsert("youtube0001", "First", 120)

    assert queue.current_playing() is None
    assert queue.current_active() is None
    assert queue.peek_next() is None
    assert queue.reserve_next() is None
    assert queue.cleanup_done(keep=1) == 0
    queue_id = queue.enqueue_after_current(track_id)
    reserved = queue.reserve_next()
    assert reserved is not None
    assert reserved[0].id == queue_id
    queue.release_queued(queue_id)
    assert queue.peek_next() is not None
    queue.reserve_next()
    assert queue.skip_current() == 1
    assert queue.skip_current() == 0


def test_queue_sort_collision_paths(database: Database) -> None:
    tracks = _tracks(database)
    queue = _queue(database)
    playing_track = tracks.upsert("youtube0001", "Playing", 120)
    pending_track = tracks.upsert("youtube0002", "Pending", 120)
    inserted_track = tracks.upsert("youtube0003", "Inserted", 120)
    next_track = tracks.upsert("youtube0004", "Next", 120)

    playing_queue = queue.enqueue(playing_track, sort_key=100.0)
    queue.mark_playing(playing_queue)
    # Проверяем защитную ветку: pending выше playing не должен ломать вставку.
    queue.enqueue(pending_track, sort_key=120.0)

    inserted_queue = queue.enqueue_after_current(inserted_track)
    assert inserted_queue > 0

    top_inserted = queue.enqueue_next(next_track)
    assert top_inserted > 0


def test_offers_repo_paths(database: Database) -> None:
    tracks = _tracks(database)
    offers = _offers(database)
    track_id = tracks.upsert("youtube0001", "Track", 120)

    offer_id = offers.add("https://youtu.be/x", submitted_by="u", note="n")
    assert offers.get_by_url("missing") is None
    assert offers.get_by_url("https://youtu.be/x") is not None
    assert len(offers.list(status="new")) == 1
    assert len(offers.list()) == 1

    offers.annotate_meta(offer_id, youtube_id="youtube0001", title="Track", duration_sec=120)
    offers.annotate_meta(offer_id)
    offers.accept(offer_id, track_id)
    accepted = offers.get_by_url("https://youtu.be/x")
    assert accepted is not None
    assert accepted.status == "accepted"
    assert accepted.accepted_track_id == track_id

    cancelled_id = offers.add("https://youtu.be/y")
    offers.cancel(cancelled_id)
    cancelled = offers.get_by_url("https://youtu.be/y")
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    offers.soft_delete(track_id)
    assert tracks.get(track_id).deleted_at is not None
    offers.restore(track_id)
    assert tracks.get(track_id).deleted_at is None


def test_config_row_mapping(database: Database) -> None:
    with database.session() as session:
        session.add(ConfigRow(key="queue.sort_step", value="0.005"))

    with database.session() as session:
        row = session.get(ConfigRow, "queue.sort_step")
        assert row is not None
        assert row.value == "0.005"


def test_text_helper_accepts_non_datetime_value() -> None:
    assert _text("raw") == "raw"
