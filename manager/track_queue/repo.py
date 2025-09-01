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
        Uses RETURNING when available, falls back otherwise.
        """
        conn = self.db.connect()
        try:
            self.db.logger.debug(
                "upsert SQL insert/update",
                youtube_id=youtube_id,
                title=title,
                duration_sec=duration_sec,
            )
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
            track_id = int(row[0]) if row is not None else self.get_id_by_youtube_id(youtube_id)
            self.db.logger.debug("upsert success", youtube_id=youtube_id, track_id=track_id)
            return track_id
        except sqlite3.OperationalError as e:
            self.db.logger.error("upsert OperationalError", youtube_id=youtube_id, error=repr(e))

        with contextlib.suppress(sqlite3.IntegrityError):
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


# --- Queue (sort_key-based ordering) -----------------------------------------


@dataclass(frozen=True)
class QueueRepo:
    db: Database

    # ---- helpers (internal) ----

    def _get_top_pending_sort_key(self) -> float | None:
        """
        Returns the highest sort_key among 'pending'. If none or all NULL -> None.
        """
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                """
            SELECT sort_key
            FROM queue_items
            WHERE status = 'pending'
            ORDER BY sort_key DESC
            LIMIT 1
            """
            )
            .fetchone()
        )
        if row is None:
            return None
        val = row["sort_key"]
        return float(val) if val is not None else None

    def _get_current_playing_sort_key(self) -> float | None:
        # noinspection SqlResolve
        row = (
            self.db.connect()
            .execute(
                """
            SELECT sort_key
            FROM queue_items
            WHERE status = 'playing'
            ORDER BY started_at DESC
            LIMIT 1
            """
            )
            .fetchone()
        )
        if row is None:
            return None
        v = row["sort_key"]
        return float(v) if v is not None else None

    def _insert_item(
        self,
        track_id: int,
        *,
        requested_by: str | None,
        note: str | None,
        sort_key: float | None,
        status: str = "pending",
    ) -> int:
        """
        Low-level insert that sets sort_key explicitly (or leaves NULL).
        """
        # noinspection SqlResolve
        cur = self.db.connect().execute(
            """
            INSERT INTO queue_items (track_id, status, requested_by, note, sort_key)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
            """,
            (track_id, status, requested_by, note, sort_key),
        )
        row = cur.fetchone()
        if row is None:
            cur2 = self.db.connect().execute("SELECT last_insert_rowid()")
            return int(cur2.fetchone()[0])
        return int(row[0])

    # ---- public API ----

    def enqueue(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
        sort_key: float | None = None,
    ) -> int:
        """
        Enqueue a track with an explicit sort_key (or None).
        The v3 trigger will auto-set sort_key for pending when NULL.
        """
        return self._insert_item(
            track_id,
            requested_by=requested_by,
            note=note,
            sort_key=sort_key,
            status="pending",
        )

    def enqueue_next(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> int:
        """
        Place as next pending: use top_pending - STEP (explicit).
        """
        step = 0.005
        top = self._get_top_pending_sort_key()
        if top is None:
            playing = self._get_current_playing_sort_key()
            base = playing if playing is not None else 100.0
            new_key = base - step
        else:
            new_key = float(top) - step
        return self._insert_item(
            track_id,
            requested_by=requested_by,
            note=note,
            sort_key=new_key,
            status="pending",
        )

    def enqueue_after_current(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> int:
        """
        Insert immediately after the currently playing item.
        """
        playing = self._get_current_playing_sort_key()
        top = self._get_top_pending_sort_key()
        if playing is None:
            playing = 100.0
        if top is None:
            new_key = playing - 0.005
        else:
            new_key = (playing + top) / 2.0
            if not (top < playing):
                new_key = playing - 0.0025
        return self._insert_item(
            track_id,
            requested_by=requested_by,
            note=note,
            sort_key=new_key,
            status="pending",
        )

    def current_playing(self) -> tuple[QueueItem, Track] | None:
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
        return QueueItem.from_row(row), Track.from_row(row)

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
            ORDER BY (qi.sort_key IS NULL), qi.sort_key DESC, qi.id
            LIMIT 1
            """
            )
            .fetchone()
        )
        if row is None:
            return None
        return QueueItem.from_row(row), Track.from_row(row)

    def mark_playing(self, queue_id: int) -> None:
        self.db.connect().execute(
            """
            UPDATE queue_items
            SET status='playing'
            WHERE id=? AND status IN ('pending','skipped')
            """,
            (queue_id,),
        )
        # v2/v3 triggers will set started_at.

    def mark_done(self, queue_id: int, *, skipped: bool = False) -> None:
        status = "skipped" if skipped else "done"
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE queue_items
            SET status=?
            WHERE id=?
            """,
            (status, queue_id),
        )
        # v2/v3 triggers will set finished_at.

    def list_visible(self, limit: int = 100) -> list[tuple[QueueItem, Track]]:
        """
        Visible to users: 'playing' first, then 'pending' by sort_key desc.
        Keep NULL sort_key after non-NULL (simulate NULLS LAST for DESC).
        """
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
                (qi.sort_key IS NULL),
                qi.sort_key DESC,
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
        """
        Trim history of done/skipped items leaving last N by finished_at / enqueued_at.
        """
        conn = self.db.connect()
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

    def soft_delete(self, track_id: int) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE tracks
            SET deleted_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
            WHERE id = ? AND deleted_at IS NULL
            """,
            (track_id,),
        )

    def restore(self, track_id: int) -> None:
        # noinspection SqlResolve
        self.db.connect().execute(
            """
            UPDATE tracks
            SET deleted_at = NULL
            WHERE id = ?
            """,
            (track_id,),
        )
