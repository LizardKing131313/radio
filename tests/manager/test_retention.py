from __future__ import annotations

import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from manager.config import AppConfig
from manager.retention import (
    FileRecord,
    apply_retention_plan,
    run_retention,
    select_audio_plan,
    select_backup_plan,
)
from manager.track_queue.db import Database
from manager.track_queue.orm import Base
from manager.track_queue.repo import QueueRepo, TracksRepo


def _record(path: Path, mtime: int, size: int) -> FileRecord:
    path.write_bytes(b"x" * size)
    os.utime(path, (mtime, mtime))
    return FileRecord(path=path, mtime=float(mtime), size=size)


def test_audio_plan_removes_oldest_unprotected_files_until_quota(tmp_path: Path) -> None:
    old = _record(tmp_path / "old.opus", 1, 4)
    protected = _record(tmp_path / "protected.opus", 2, 4)
    newest = _record(tmp_path / "newest.opus", 3, 4)

    plan = select_audio_plan(
        [old, protected, newest],
        quota_bytes=8,
        protected_paths=[protected.path],
    )

    assert plan.selected == (old.path,)
    assert plan.protected == (protected.path,)
    assert plan.skipped == (newest.path,)


def test_dry_run_does_not_delete_and_records_failures(tmp_path: Path) -> None:
    removable = _record(tmp_path / "remove.opus", 1, 4)
    failed = _record(tmp_path / "failed.opus", 2, 4)
    plan = select_audio_plan([removable, failed], quota_bytes=0, protected_paths=[])

    dry_run = apply_retention_plan(plan, dry_run=True)
    assert dry_run.deleted == ()
    assert dry_run.failed == ()
    assert removable.path.exists()

    def fail_unlink(_path: Path) -> None:
        raise OSError("permission denied")

    result = apply_retention_plan(plan, dry_run=False, unlink=fail_unlink)
    assert result.deleted == ()
    assert result.failed == (removable.path, failed.path)

    success = apply_retention_plan(
        select_audio_plan([removable], quota_bytes=0, protected_paths=[]),
        dry_run=False,
    )
    assert success.deleted == (removable.path,)
    assert not removable.path.exists()


def test_backup_plan_keeps_newest_recognized_dumps_and_ignores_other_files(
    tmp_path: Path,
) -> None:
    old = _record(tmp_path / "radio-20260101T000000Z.dump", 1, 1)
    newest = _record(tmp_path / "radio-20260102T000000Z.dump", 2, 1)
    unrelated = _record(tmp_path / "notes.dump", 0, 1)

    plan = select_backup_plan(
        [old, newest, unrelated],
        keep_count=1,
    )

    assert plan.selected == (old.path,)
    assert plan.protected == (newest.path,)
    assert plan.skipped == (unrelated.path,)


def test_retention_command_dry_run_keeps_fixture_files(tmp_path: Path) -> None:
    cfg = AppConfig()
    cfg.database.dsn_raw = SecretStr(f"sqlite+pysqlite:///{tmp_path / 'retention.db'}")
    cfg.paths.cache_cold = tmp_path / "cold"
    cfg.paths.cache_hot = tmp_path / "hot"
    cfg.paths.backup_dir = tmp_path / "postgres"
    cfg.prefetch.cold_quota_bytes = 1
    cfg.retention.backup_keep_count = 1
    cfg.paths.cache_cold.mkdir(parents=True)
    cfg.paths.backup_dir.mkdir(parents=True)

    database = Database(app_config=cfg)
    Base.metadata.create_all(database.engine)
    track = _record(cfg.paths.cache_cold / "protected.opus", 1, 2)
    track_id = TracksRepo(database).upsert("protected", "Protected", 120)
    TracksRepo(database).update_track_audio(track_id=track_id, audio_path=str(track.path))
    queued_id = TracksRepo(database).upsert("queued", "Queued", 120, is_active=0)
    queued_path = _record(cfg.paths.cache_cold / "queued.opus", 2, 2)
    TracksRepo(database).update_track_audio(track_id=queued_id, audio_path=str(queued_path.path))
    QueueRepo(database).enqueue(queued_id)
    no_audio_id = TracksRepo(database).upsert(
        "queued-no-audio", "Queued no audio", 120, is_active=0
    )
    QueueRepo(database).enqueue(no_audio_id)
    database.close()

    removable_backup = _record(cfg.paths.backup_dir / "radio-20260101T000000Z.dump", 1, 1)
    retained_backup = _record(cfg.paths.backup_dir / "radio-20260102T000000Z.dump", 2, 1)

    assert run_retention(config=cfg, dry_run=True) == 0
    assert track.path.exists()
    assert removable_backup.path.exists()
    assert retained_backup.path.exists()


def test_file_records_skips_directories_and_unreadable_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from manager.retention import file_records

    (tmp_path / "nested").mkdir()
    unreadable = _record(tmp_path / "unreadable.opus", 1, 1)
    original_stat = Path.stat

    def fake_stat(path: Path, *args: object, **kwargs: object) -> object:
        if path == unreadable.path:
            raise OSError("stat failed")
        return original_stat(path)

    monkeypatch.setattr(Path, "stat", fake_stat)

    assert file_records(tmp_path) == []
