from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.track_queue.db import Database
from manager.track_queue.repo import QueueRepo, TracksRepo

BACKUP_NAME = re.compile(r"^radio-\d{8}T\d{6}Z\.dump$")


@dataclass(frozen=True)
class FileRecord:
    path: Path
    mtime: float
    size: int


@dataclass(frozen=True)
class RetentionPlan:
    selected: tuple[Path, ...]
    protected: tuple[Path, ...]
    skipped: tuple[Path, ...]


@dataclass(frozen=True)
class RetentionResult:
    deleted: tuple[Path, ...]
    failed: tuple[Path, ...]


def select_audio_plan(
    files: Iterable[FileRecord],
    *,
    quota_bytes: int,
    protected_paths: Iterable[Path],
) -> RetentionPlan:
    """Select oldest unprotected audio files until the byte quota is met."""
    records = sorted(files, key=lambda item: (item.mtime, item.path.as_posix()))
    protected = {_normalized(path) for path in protected_paths}
    protected_records = [record for record in records if _normalized(record.path) in protected]
    total = sum(record.size for record in records)
    selected: list[Path] = []
    skipped: list[Path] = []

    for record in records:
        if _normalized(record.path) in protected:
            continue
        if total <= max(0, quota_bytes):
            skipped.append(record.path)
            continue
        selected.append(record.path)
        total -= record.size

    return RetentionPlan(
        selected=tuple(selected),
        protected=tuple(record.path for record in protected_records),
        skipped=tuple(skipped),
    )


def select_backup_plan(files: Iterable[FileRecord], *, keep_count: int) -> RetentionPlan:
    """Select old recognized dumps while leaving newer and unrelated files alone."""
    records = list(files)
    recognized = sorted(
        (record for record in records if BACKUP_NAME.fullmatch(record.path.name)),
        key=lambda item: (-item.mtime, item.path.as_posix()),
    )
    keep = max(0, keep_count)
    return RetentionPlan(
        selected=tuple(record.path for record in recognized[keep:]),
        protected=tuple(record.path for record in recognized[:keep]),
        skipped=tuple(
            record.path for record in records if not BACKUP_NAME.fullmatch(record.path.name)
        ),
    )


def apply_retention_plan(
    plan: RetentionPlan,
    *,
    dry_run: bool,
    unlink: Callable[[Path], None] | None = None,
) -> RetentionResult:
    if dry_run:
        return RetentionResult(deleted=(), failed=())

    remove = unlink or (lambda path: path.unlink())
    deleted: list[Path] = []
    failed: list[Path] = []
    for path in plan.selected:
        try:
            remove(path)
        except OSError:
            failed.append(path)
        else:
            deleted.append(path)
    return RetentionResult(deleted=tuple(deleted), failed=tuple(failed))


def file_records(directory: Path) -> list[FileRecord]:
    records: list[FileRecord] = []
    for path in directory.iterdir() if directory.exists() else ():
        try:
            if not path.is_file():
                continue
            stat = path.stat()
        except OSError:
            continue
        records.append(FileRecord(path=path, mtime=stat.st_mtime, size=stat.st_size))
    return records


def run_retention(*, config: AppConfig | None = None, dry_run: bool = True) -> int:
    """Run an operator-invoked retention pass; deletion requires explicit --delete."""
    cfg = config or get_settings()
    database = Database(app_config=cfg)
    log = get_logger("retention")
    try:
        database.ensure_schema()
        tracks = TracksRepo(database)
        queue = QueueRepo(database)
        protected = {Path(path) for path in tracks.list_audio_paths(status="active")}
        for _item, track in queue.list_visible(limit=10000):
            if track.audio_path:
                protected.add(Path(track.audio_path))

        audio_plan = select_audio_plan(
            [
                record
                for record in file_records(cfg.paths.cache_cold)
                if record.path.suffix.lower() == ".opus"
            ],
            quota_bytes=cfg.prefetch.cold_quota_bytes,
            protected_paths=protected,
        )
        backup_plan = select_backup_plan(
            file_records(cfg.paths.backup_dir),
            keep_count=cfg.retention.backup_keep_count,
        )
        audio_result = apply_retention_plan(audio_plan, dry_run=dry_run)
        backup_result = apply_retention_plan(backup_plan, dry_run=dry_run)
        log.info(
            "retention complete",
            dry_run=dry_run,
            audio_selected=[str(path) for path in audio_plan.selected],
            audio_protected=[str(path) for path in audio_plan.protected],
            audio_skipped=[str(path) for path in audio_plan.skipped],
            audio_deleted=len(audio_result.deleted),
            audio_failed=[str(path) for path in audio_result.failed],
            backups_selected=[str(path) for path in backup_plan.selected],
            backups_protected=[str(path) for path in backup_plan.protected],
            backups_skipped=[str(path) for path in backup_plan.skipped],
            backups_deleted=len(backup_result.deleted),
            backups_failed=[str(path) for path in backup_result.failed],
        )
        return 1 if audio_result.failed or backup_result.failed else 0
    finally:
        database.close()


def _normalized(path: Path) -> Path:
    return path.resolve(strict=False)


__all__ = [
    "FileRecord",
    "RetentionPlan",
    "RetentionResult",
    "apply_retention_plan",
    "file_records",
    "select_audio_plan",
    "select_backup_plan",
]
