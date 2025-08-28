from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path


# --- Simple SQL migrations (embedded) -----------------------------------------
# Версионирование максимально простое: числовые версии, один файл на версию.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id             INTEGER PRIMARY KEY,
            youtube_id     TEXT NOT NULL UNIQUE,
            title          TEXT NOT NULL,
            duration_sec   INTEGER NOT NULL,
            channel        TEXT,
            url            TEXT NOT NULL,
            thumbnail_url  TEXT,
            audio_path     TEXT,
            loudness_lufs  REAL,
            added_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            last_played_at TEXT,
            play_count     INTEGER NOT NULL DEFAULT 0,
            is_active      INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title);
        CREATE INDEX IF NOT EXISTS idx_tracks_added_at ON tracks(added_at);

        CREATE TABLE IF NOT EXISTS queue_items (
            id           INTEGER PRIMARY KEY,
            track_id     INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','playing','done','skipped')),
            priority     INTEGER NOT NULL DEFAULT 0,
            requested_by TEXT,
            note         TEXT,
            enqueued_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            started_at   TEXT,
            finished_at  TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_queue_pending_order
            ON queue_items(status, priority DESC, enqueued_at ASC);
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);

        CREATE TABLE IF NOT EXISTS offers (
            id                 INTEGER PRIMARY KEY,
            youtube_url        TEXT NOT NULL UNIQUE,
            youtube_id         TEXT,
            title              TEXT,
            duration_sec       INTEGER,
            channel            TEXT,
            submitted_by       TEXT,
            note               TEXT,
            status             TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','accepted','cancelled')),
            accepted_track_id  INTEGER,
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            processed_at       TEXT,
            FOREIGN KEY (accepted_track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_offers_status_created
            ON offers(status, created_at DESC);
        """,  # noqa: E501
    ),
    # v2 — anti-spam + sort_key + triggers
    (
        2,
        """
        PRAGMA foreign_keys=ON;

        -- 5) Anti-spam: allow only one 'pending' item per track at a time.
        -- Requires SQLite 3.8+ (partial indexes).
        CREATE UNIQUE INDEX IF NOT EXISTS uq_queue_pending_unique_track
        ON queue_items(track_id)
        WHERE status = 'pending';

        -- 7) Stable ordering key to enable infinite "insert after current" without re-numbering.
        ALTER TABLE queue_items ADD COLUMN sort_key REAL;

        -- Backfill sort_key:
        --  - 'playing' gets 100.0 (the "top" anchor);
        --  - 'pending' get descending values below 100.0 by current order;
        --  - others remain NULL.
        UPDATE queue_items
           SET sort_key = 100.0
         WHERE status = 'playing' AND sort_key IS NULL;

        CREATE TEMP TABLE q_order(id INTEGER PRIMARY KEY, rn INTEGER);
        INSERT INTO q_order
        SELECT id,
               ROW_NUMBER() OVER (
                 ORDER BY priority DESC, enqueued_at ASC, id ASC
               ) AS rn
          FROM queue_items
         WHERE status = 'pending';

        UPDATE queue_items
           SET sort_key = 100.0 - 0.01 * (SELECT rn FROM q_order WHERE q_order.id = queue_items.id)
         WHERE id IN (SELECT id FROM q_order) AND sort_key IS NULL;

        DROP TABLE q_order;

        -- Helpful indexes for new ordering:
        CREATE INDEX IF NOT EXISTS idx_queue_status_sort
          ON queue_items(status, sort_key DESC);

        -- 8) Triggers for timestamp consistency on status changes.
        -- When a row becomes 'playing' and started_at is not set, stamp it.
        CREATE TRIGGER IF NOT EXISTS trg_queue_started
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status = 'playing' AND NEW.started_at IS NULL
        BEGIN
            UPDATE queue_items
               SET started_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;

        -- When a row becomes 'done' or 'skipped' and finished_at is not set, stamp it.
        CREATE TRIGGER IF NOT EXISTS trg_queue_finished
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status IN ('done','skipped') AND NEW.finished_at IS NULL
        BEGIN
            UPDATE queue_items
               SET finished_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;
        """,
    ),
]


@dataclass(frozen=True)
class DatabaseConfig:
    path: Path
    pragmas: Sequence[str] = (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA temp_store=MEMORY",
        "PRAGMA foreign_keys=ON",
    )


class Database:
    """Thin SQLite wrapper with simple SQL migrations."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._conn: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(self._config.path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._apply_pragmas(self._conn)
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            conn.execute("BEGIN")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    # --- migrations -----------------------------------------------------------

    def ensure_schema(self) -> None:
        """Apply all pending embedded migrations."""
        with self.tx() as conn:
            self._bootstrap_schema_migrations(conn)
            current = self._current_version(conn)
            for version, sql in sorted(MIGRATIONS, key=lambda x: x[0]):
                if version > current:
                    conn.executescript(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations(version) VALUES (?)",
                        (version,),
                    )

    # --- helpers --------------------------------------------------------------

    def _apply_pragmas(self, conn: sqlite3.Connection) -> None:
        cur = conn.cursor()
        for p in self._config.pragmas:
            cur.execute(p)
        cur.close()

    @staticmethod
    def _bootstrap_schema_migrations(conn: sqlite3.Connection) -> None:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     INTEGER PRIMARY KEY,
                applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            )
            """
        )

    @staticmethod
    def _current_version(conn: sqlite3.Connection) -> int:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"]) if row and row["v"] is not None else 0


# --- CLI: init/migrate --------------------------------------------------------


def _cli() -> None:
    parser = argparse.ArgumentParser(
        prog="queue-db",
        description="SQLite migrations for radio queue.",
    )
    parser.add_argument(
        "--db",
        dest="db_path",
        type=Path,
        required=True,
        help="Path to SQLite database file (will be created if absent).",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="Apply embedded SQL migrations.")
    args = parser.parse_args()

    config = DatabaseConfig(path=args.db_path)
    db = Database(config)
    if args.cmd == "migrate":
        db.ensure_schema()
        # No prints/logs here; keep runtime clean.

    db.close()


if __name__ == "__main__":
    _cli()
