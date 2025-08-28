from __future__ import annotations

import contextlib
import sqlite3
from dataclasses import dataclass

from .db import Database
from .models import Offer, QueueItem, Track


# Репозитории: только SQL, без бизнес-логики плеера.


# --- Tracks -------------------------------------------------------------------


@dataclass(frozen=True)
class TracksRepo:
    db: Database

    def upsert(
        self,
        youtube_id: str,
        title: str,
        duration_sec: int,
        url: str,
        *,
        channel: str | None = None,
        thumbnail_url: str | None = None,
        audio_path: str | None = None,
        loudness_lufs: float | None = None,
        is_active: int = 1,
    ) -> int:
        """
        Insert-or-update by unique youtube_id, return track id.
        Uses RETURNING where supported.
        """
        conn = self.db.connect()
        try:
            # noinspection SqlResolve
            cur = conn.execute(
                """
                INSERT INTO tracks (youtube_id, title, duration_sec, url, channel, thumbnail_url, audio_path, loudness_lufs, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(youtube_id) DO UPDATE SET
                    title=excluded.title,
                    duration_sec=excluded.duration_sec,
                    url=excluded.url,
                    channel=excluded.channel,
                    thumbnail_url=excluded.thumbnail_url,
                    audio_path=excluded.audio_path,
                    loudness_lufs=excluded.loudness_lufs,
                    is_active=excluded.is_active
                    RETURNING id
                """,  # noqa: E501
                (
                    youtube_id,
                    title,
                    duration_sec,
                    url,
                    channel,
                    thumbnail_url,
                    audio_path,
                    loudness_lufs,
                    is_active,
                ),
            )
            row = cur.fetchone()
            return int(row[0]) if row is not None else self.get_id_by_youtube_id(youtube_id)
        except sqlite3.OperationalError:
            # Fallback for very old SQLite without RETURNING
            pass

        with contextlib.suppress(sqlite3.IntegrityError):
            # noinspection SqlResolve
            conn.execute(
                """
                INSERT INTO tracks (youtube_id, title, duration_sec, url, channel, thumbnail_url, audio_path, loudness_lufs, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,  # noqa: E501
                (
                    youtube_id,
                    title,
                    duration_sec,
                    url,
                    channel,
                    thumbnail_url,
                    audio_path,
                    loudness_lufs,
                    is_active,
                ),
            )
        return self.get_id_by_youtube_id(youtube_id)

    def get_id_by_youtube_id(self, youtube_id: str) -> int:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                "SELECT id FROM tracks WHERE youtube_id = ?",
                (youtube_id,),
            )
            .fetchone()
        )
        if row is None:
            raise KeyError("track not found")
        return int(row["id"])

    def get(self, track_id: int) -> Track:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                "SELECT * FROM tracks WHERE id = ?",
                (track_id,),
            )
            .fetchone()
        )
        if row is None:
            raise KeyError("track not found")
        return Track.from_row(row)

    def touch_play(self, track_id: int) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE tracks
            SET last_played_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                play_count = play_count + 1
            WHERE id = ?
            """,
            (track_id,),
        )


# --- Queue --------------------------------------------------------------------


@dataclass(frozen=True)
class QueueRepo:
    db: Database

    def enqueue(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
        priority: int = 0,
    ) -> int:
        # noinspection SqlResolve
        cur = self.db.connect().execute(
            """
            INSERT INTO queue_items (track_id, status, priority, requested_by, note)
            VALUES (?, 'pending', ?, ?, ?)
                RETURNING id
            """,
            (track_id, priority, requested_by, note),
        )
        row = cur.fetchone()
        if row is None:
            cur2 = self.db.connect().execute("SELECT last_insert_rowid()")
            return int(cur2.fetchone()[0])
        return int(row[0])

    def enqueue_next(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> int:
        # Берём максимальный priority среди pending и ставим +1
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                "SELECT COALESCE(MAX(priority), 0) AS p FROM queue_items WHERE status = 'pending'"
            )
            .fetchone()
        )
        next_priority = int(row["p"]) + 1 if row is not None else 1
        return self.enqueue(
            track_id,
            requested_by=requested_by,
            note=note,
            priority=next_priority,
        )

    def current_playing(self) -> tuple[QueueItem, Track] | None:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                """
            SELECT qi.*, t.*
            FROM queue_items qi
                     JOIN tracks t ON t.id = qi.track_id
            WHERE qi.status = 'playing'
            ORDER BY qi.started_at DESC
            LIMIT 1
            """
            )
            .fetchone()
        )
        if row is None:
            return None
        qi = QueueItem.from_row(row)
        t = Track.from_row(row)
        return qi, t

    def peek_next(self) -> tuple[QueueItem, Track] | None:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                """
            SELECT qi.*, t.*
            FROM queue_items qi
                     JOIN tracks t ON t.id = qi.track_id
            WHERE qi.status = 'pending'
            ORDER BY qi.priority DESC, qi.enqueued_at, qi.id
            LIMIT 1
            """
            )
            .fetchone()
        )
        if row is None:
            return None
        return QueueItem.from_row(row), Track.from_row(row)

    def mark_playing(self, queue_id: int) -> None:
        conn = self.db.connect()
        # noinspection SqlResolve
        conn.execute(
            """
            UPDATE queue_items
            SET status='playing',
                started_at=(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            WHERE id=? AND status IN ('pending','skipped')
            """,
            (queue_id,),
        )

    def mark_done(self, queue_id: int, *, skipped: bool = False) -> None:
        status = "skipped" if skipped else "done"
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE queue_items
            SET status=?,
                finished_at=(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            WHERE id=?
            """,
            (status, queue_id),
        )

    def list_visible(self, limit: int = 100) -> list[tuple[QueueItem, Track]]:
        # noinspection SqlResolve
        rows = (
            self.db.connect()
            .execute(
                """
            SELECT qi.*, t.*
            FROM queue_items qi
                     JOIN tracks t ON t.id = qi.track_id
            WHERE qi.status IN ('playing','pending')
            ORDER BY
                CASE qi.status WHEN 'playing' THEN 1 ELSE 2 END,
                qi.priority DESC,
                qi.enqueued_at,
                qi.id
                LIMIT ?
            """,
                (limit,),
            )
            .fetchall()
        )
        result: list[tuple[QueueItem, Track]] = []
        for r in rows:
            result.append((QueueItem.from_row(r), Track.from_row(r)))
        return result

    def cleanup_done(self, keep: int = 500) -> int:
        # Хвост истории чистим: оставляем последние N done/skipped по finished_at
        conn = self.db.connect()
        # noinspection SqlResolve
        row = conn.execute(
            """
            WITH ordered AS (
                SELECT id,
                       ROW_NUMBER() OVER (ORDER BY COALESCE(finished_at,enqueued_at) DESC) AS rn
                FROM queue_items
                WHERE status IN ('done','skipped')
            )
            DELETE FROM queue_items
            WHERE id IN (SELECT id FROM ordered WHERE rn > ?)
            """,
            (keep,),
        )
        return row.rowcount if hasattr(row, "rowcount") else 0


# --- Offers -------------------------------------------------------------------


@dataclass(frozen=True)
class OffersRepo:
    db: Database

    def add(
        self, youtube_url: str, *, submitted_by: str | None = None, note: str | None = None
    ) -> int:
        # noinspection SqlResolve
        cur = self.db.connect().execute(
            """
            INSERT INTO offers (youtube_url, submitted_by, note)
            VALUES (?, ?, ?)
                RETURNING id
            """,
            (youtube_url, submitted_by, note),
        )
        r = cur.fetchone()
        if r is None:
            cur2 = self.db.connect().execute("SELECT last_insert_rowid()")
            return int(cur2.fetchone()[0])
        return int(r[0])

    def get_by_url(self, youtube_url: str) -> Offer | None:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                "SELECT * FROM offers WHERE youtube_url = ?",
                (youtube_url,),
            )
            .fetchone()
        )
        return Offer.from_row(row) if row is not None else None

    def list(self, *, status: str | None = None, limit: int = 200) -> list[Offer]:
        if status:
            # noinspection SqlResolve
            rows = (
                self.db.connect()
                .execute(
                    """
                SELECT * FROM offers
                WHERE status = ?
                ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (status, limit),
                )
                .fetchall()
            )
        else:
            # noinspection SqlResolve
            rows = (
                self.db.connect()
                .execute(
                    """
                SELECT * FROM offers
                ORDER BY created_at DESC
                    LIMIT ?
                """,
                    (limit,),
                )
                .fetchall()
            )
        return [Offer.from_row(r) for r in rows]

    def accept(self, offer_id: int, track_id: int) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE offers
            SET status='accepted',
                accepted_track_id=?,
                processed_at=(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            WHERE id=? AND status='new'
            """,
            (track_id, offer_id),
        )

    def cancel(self, offer_id: int) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE offers
            SET status='cancelled',
                processed_at=(strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            WHERE id=? AND status='new'
            """,
            (offer_id,),
        )

    def annotate_meta(
        self,
        offer_id: int,
        *,
        youtube_id: str | None = None,
        title: str | None = None,
        duration_sec: int | None = None,
        channel: str | None = None,
    ) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE offers
            SET youtube_id = COALESCE(?, youtube_id),
                title = COALESCE(?, title),
                duration_sec = COALESCE(?, duration_sec),
                channel = COALESCE(?, channel)
            WHERE id = ?
            """,
            (youtube_id, title, duration_sec, channel, offer_id),
        )
