from __future__ import annotations

import argparse
import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from manager.config import AppConfig, get_settings
from manager.logger import get_logger
from manager.track_queue.migrations import MIGRATIONS


@dataclass
class DatabaseConfig:
    pragmas: Sequence[str] = (
        "PRAGMA journal_mode=WAL",
        "PRAGMA synchronous=NORMAL",
        "PRAGMA temp_store=MEMORY",
        "PRAGMA foreign_keys=ON",
        "PRAGMA busy_timeout=5000",
    )


class Database:
    """Thin SQLite wrapper with simple SQL migrations."""

    def __init__(self, app_config: AppConfig | None = None, path: Path | str | None = None) -> None:
        cfg = app_config or get_settings()
        self._path = Path(path) if path else cfg.paths.data_base
        self._database_config = DatabaseConfig()
        self._conn: sqlite3.Connection | None = None
        self.logger = get_logger("data_base")
        self.logger.info("Database initialized", path=self._path)

    def connect(self) -> sqlite3.Connection:
        if self._conn is None:
            # ВАЖНО: autocommit
            self._conn = sqlite3.connect(self._path, check_same_thread=False, isolation_level=None)
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
        for p in self._database_config.pragmas:
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

    db = Database(path=args.db_path)
    if args.cmd == "migrate":
        db.ensure_schema()
        # Keep CLI quiet.

    db.close()


if __name__ == "__main__":
    _cli()
