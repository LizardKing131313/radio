from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import delete, func, select, update

from .db import Database
from .models import QueueItem, Track
from .orm import QueueItemRow, TrackRow, queue_item_from_orm, track_from_orm
from .orm_typing import orm_int, rowcount


@dataclass(frozen=True)
class QueueRepo:
    # Очередь сортируется числовым sort_key: большее значение ближе к началу.
    db: Database

    def _get_top_pending_sort_key(self) -> float | None:
        with self.db.session() as session:
            sort_key = session.scalar(
                select(QueueItemRow.sort_key)
                .where(QueueItemRow.status == "pending")
                .order_by(QueueItemRow.sort_key.is_(None), QueueItemRow.sort_key.desc())
                .limit(1)
            )
            return float(sort_key) if sort_key is not None else None

    def _get_current_playing_sort_key(self) -> float | None:
        with self.db.session() as session:
            sort_key = session.scalar(
                select(QueueItemRow.sort_key)
                .where(QueueItemRow.status == "playing")
                .order_by(QueueItemRow.started_at.is_(None), QueueItemRow.started_at.desc())
                .limit(1)
            )
            return float(sort_key) if sort_key is not None else None

    def _insert_item(
        self,
        track_id: int,
        *,
        requested_by: str | None,
        note: str | None,
        sort_key: float | None,
        status: str = "pending",
    ) -> int:
        with self.db.session() as session:
            row = QueueItemRow(
                track_id=track_id,
                status=status,
                requested_by=requested_by,
                note=note,
                sort_key=sort_key,
            )
            session.add(row)
            session.flush()
            return orm_int(row.id)

    def enqueue(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
        sort_key: float | None = None,
    ) -> int:
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
        # Вставка "следующим" ставит элемент выше текущего top pending.
        step = 0.005
        top = self._get_top_pending_sort_key()
        if top is None:
            playing = self._get_current_playing_sort_key()
            base = playing if playing is not None else 100.0
            new_key = base - step
        else:
            new_key = top + step
        return self._insert_item(
            track_id,
            requested_by=requested_by,
            note=note,
            sort_key=new_key,
            status="pending",
        )

    def enqueue_immediate(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> tuple[int, int]:
        # Для "играть сейчас" заменяем старые active items и pending-дубль этого
        # трека в той же транзакции. Так queue-player не успевает запушить другой
        # pending item между командами админки, а повторный клик не падает на
        # unique index по pending/queued track_id.
        step = 0.005
        with self.db.session() as session:
            playing = session.scalar(
                select(QueueItemRow.sort_key)
                .where(QueueItemRow.status == "playing")
                .order_by(QueueItemRow.started_at.is_(None), QueueItemRow.started_at.desc())
                .limit(1)
            )
            result = session.execute(
                update(QueueItemRow)
                .where(
                    (QueueItemRow.status.in_(("queued", "playing")))
                    | ((QueueItemRow.track_id == track_id) & (QueueItemRow.status == "pending"))
                )
                .values(status="skipped", finished_at=func.now())
            )
            top = session.scalar(
                select(QueueItemRow.sort_key)
                .where(QueueItemRow.status == "pending")
                .order_by(QueueItemRow.sort_key.is_(None), QueueItemRow.sort_key.desc())
                .limit(1)
            )
            if top is None:
                base = float(playing) if playing is not None else 100.0
                sort_key = base - step
            else:
                sort_key = float(top) + step
            row = QueueItemRow(
                track_id=track_id,
                status="queued",
                requested_by=requested_by,
                note=note,
                sort_key=sort_key,
            )
            session.add(row)
            session.flush()
            return orm_int(row.id), rowcount(result)

    def enqueue_after_current(
        self,
        track_id: int,
        *,
        requested_by: str | None = None,
        note: str | None = None,
    ) -> int:
        # Вставка после текущего трека пытается попасть между playing и top pending.
        playing = self._get_current_playing_sort_key()
        top = self._get_top_pending_sort_key()
        if playing is None:
            playing = 100.0
        if top is None:
            new_key = playing - 0.005
        else:
            new_key = (playing + top) / 2.0
            if not top < playing:
                new_key = playing - 0.0025
        return self._insert_item(
            track_id,
            requested_by=requested_by,
            note=note,
            sort_key=new_key,
            status="pending",
        )

    def current_active(self) -> tuple[QueueItem, Track] | None:
        # Для playback-воркера active означает "уже отдали в Liquidsoap" или
        # "прямо сейчас играет". Так не пушим один и тот же queue item дважды.
        with self.db.session() as session:
            row = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status.in_(("queued", "playing")))
                .order_by(
                    QueueItemRow.status != "playing",
                    QueueItemRow.started_at.is_(None),
                    QueueItemRow.started_at.desc(),
                    QueueItemRow.id,
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            queue_item, track = row
            return queue_item_from_orm(queue_item), track_from_orm(track)

    def current_playing(self) -> tuple[QueueItem, Track] | None:
        with self.db.session() as session:
            row = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status == "playing")
                .order_by(QueueItemRow.started_at.is_(None), QueueItemRow.started_at.desc())
                .limit(1)
            ).first()
            if row is None:
                return None
            queue_item, track = row
            return queue_item_from_orm(queue_item), track_from_orm(track)

    def current_queued(self) -> tuple[QueueItem, Track] | None:
        with self.db.session() as session:
            row = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status == "queued")
                .order_by(
                    QueueItemRow.sort_key.is_(None),
                    QueueItemRow.sort_key.desc(),
                    QueueItemRow.id,
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            queue_item, track = row
            return queue_item_from_orm(queue_item), track_from_orm(track)

    def peek_next(self) -> tuple[QueueItem, Track] | None:
        with self.db.session() as session:
            row = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status == "pending")
                .order_by(
                    QueueItemRow.sort_key.is_(None), QueueItemRow.sort_key.desc(), QueueItemRow.id
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            queue_item, track = row
            return queue_item_from_orm(queue_item), track_from_orm(track)

    def reserve_next(self) -> tuple[QueueItem, Track] | None:
        # Берем первый pending item и переводим его в queued. Это маленькая
        # "бронь" между БД и Liquidsoap request.queue.
        with self.db.session() as session:
            row = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status == "pending")
                .order_by(
                    QueueItemRow.sort_key.is_(None), QueueItemRow.sort_key.desc(), QueueItemRow.id
                )
                .limit(1)
            ).first()
            if row is None:
                return None
            queue_item, track = row
            queue_item.status = "queued"
            session.flush()
            return queue_item_from_orm(queue_item), track_from_orm(track)

    def mark_playing(self, queue_id: int) -> None:
        with self.db.session() as session:
            session.execute(
                update(QueueItemRow)
                .where(
                    QueueItemRow.id == queue_id,
                    QueueItemRow.status.in_(("pending", "queued")),
                )
                .values(status="playing", started_at=func.now())
            )

    def mark_done(self, queue_id: int, *, skipped: bool = False) -> None:
        status = "skipped" if skipped else "done"
        with self.db.session() as session:
            session.execute(
                update(QueueItemRow)
                .where(QueueItemRow.id == queue_id)
                .values(status=status, finished_at=func.now())
            )

    def mark_failed(self, queue_id: int, error_detail: str) -> None:
        with self.db.session() as session:
            session.execute(
                update(QueueItemRow)
                .where(QueueItemRow.id == queue_id)
                .values(status="failed", error_detail=error_detail, finished_at=func.now())
            )

    def release_queued(self, queue_id: int) -> None:
        # Если Liquidsoap не принял request, возвращаем item назад в pending.
        with self.db.session() as session:
            session.execute(
                update(QueueItemRow)
                .where(QueueItemRow.id == queue_id, QueueItemRow.status == "queued")
                .values(status="pending")
            )

    def skip_current(self, queue_id: int | None = None) -> int:
        # Skip касается текущего playing item. Если playing еще нет, скипаем
        # один queued request, который уже отдан в Liquidsoap.
        with self.db.session() as session:
            if queue_id is None:
                queue_id = session.scalar(
                    select(QueueItemRow.id)
                    .where(QueueItemRow.status == "playing")
                    .order_by(QueueItemRow.started_at.is_(None), QueueItemRow.started_at.desc())
                    .limit(1)
                )
            if queue_id is None:
                queue_id = session.scalar(
                    select(QueueItemRow.id)
                    .where(QueueItemRow.status == "queued")
                    .order_by(
                        QueueItemRow.sort_key.is_(None),
                        QueueItemRow.sort_key.desc(),
                        QueueItemRow.id,
                    )
                    .limit(1)
                )
            if queue_id is None:
                return 0
            result = session.execute(
                update(QueueItemRow)
                .where(
                    QueueItemRow.id == queue_id,
                    QueueItemRow.status.in_(("queued", "playing")),
                )
                .values(status="skipped", finished_at=func.now())
            )
            return rowcount(result)

    def list_visible(self, limit: int = 100) -> list[tuple[QueueItem, Track]]:
        with self.db.session() as session:
            rows = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(
                    QueueItemRow.status.in_(("queued", "playing", "pending")),
                    TrackRow.deleted_at.is_(None),
                )
                .order_by(
                    QueueItemRow.status != "playing",
                    QueueItemRow.status != "queued",
                    QueueItemRow.sort_key.is_(None),
                    QueueItemRow.sort_key.desc(),
                    QueueItemRow.id,
                )
                .limit(limit)
            ).all()
            return [
                (queue_item_from_orm(queue_item), track_from_orm(track))
                for queue_item, track in rows
            ]

    def history(self, limit: int = 100) -> list[tuple[QueueItem, Track]]:
        with self.db.session() as session:
            rows = session.execute(
                select(QueueItemRow, TrackRow)
                .join(TrackRow, TrackRow.id == QueueItemRow.track_id)
                .where(QueueItemRow.status.in_(("done", "skipped", "failed")))
                .order_by(func.coalesce(QueueItemRow.finished_at, QueueItemRow.enqueued_at).desc())
                .limit(limit)
            ).all()
            return [
                (queue_item_from_orm(queue_item), track_from_orm(track))
                for queue_item, track in rows
            ]

    def cleanup_done(self, keep: int = 500) -> int:
        # Удержание истории очереди: последние keep завершенных строк остаются.
        with self.db.session() as session:
            old_ids = session.scalars(
                select(QueueItemRow.id)
                .where(QueueItemRow.status.in_(("done", "skipped", "failed")))
                .order_by(func.coalesce(QueueItemRow.finished_at, QueueItemRow.enqueued_at).desc())
                .offset(keep)
            ).all()
            if not old_ids:
                return 0
            session.execute(delete(QueueItemRow).where(QueueItemRow.id.in_(old_ids)))
            return len(old_ids)
