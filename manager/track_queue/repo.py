from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from .db import Database
from .models import Offer, QueueItem, Track
from .orm import (
    OfferRow,
    QueueItemRow,
    TrackRow,
    offer_from_orm,
    queue_item_from_orm,
    track_from_orm,
)


def _watch_url(youtube_id: str) -> str:
    return f"https://www.youtube.com/watch?v={youtube_id}"


@dataclass(frozen=True)
class TracksRepo:
    # Репозиторий каталога треков. Все методы здесь синхронные и короткие:
    # воркеры вызывают их напрямую, без промежуточной шины сообщений.
    db: Database

    def upsert(
        self,
        youtube_id: str,
        title: str,
        duration_sec: int,
        url: str | None = None,
        *,
        channel: str | None = None,
        thumbnail_url: str | None = None,
        audio_path: str | None = None,
        loudness_lufs: float | None = None,
        is_active: int = 1,
    ) -> int:
        # Поиск может приносить уже известный ролик. Обновляем метаданные, но не
        # затираем найденный ранее audio_path пустым значением.
        with self.db.session() as session:
            row = session.scalar(select(TrackRow).where(TrackRow.youtube_id == youtube_id))
            if row is None:
                row = TrackRow(
                    youtube_id=youtube_id,
                    title=title,
                    duration_sec=duration_sec,
                    url=url or _watch_url(youtube_id),
                    channel=channel,
                    thumbnail_url=thumbnail_url,
                    audio_path=audio_path,
                    loudness_lufs=loudness_lufs,
                    is_active=bool(is_active),
                )
                session.add(row)
            else:
                row.title = title
                row.duration_sec = duration_sec
                row.url = url or _watch_url(youtube_id)
                row.channel = channel
                row.thumbnail_url = thumbnail_url
                row.audio_path = audio_path or row.audio_path
                row.loudness_lufs = (
                    loudness_lufs if loudness_lufs is not None else row.loudness_lufs
                )
                # Поиск не должен возвращать забаненный трек обратно в каталог.
                row.is_active = bool(row.is_active) and bool(is_active)
            session.flush()
            return int(row.id)

    def get_id_by_youtube_id(self, youtube_id: str) -> int:
        with self.db.session() as session:
            track_id = session.scalar(select(TrackRow.id).where(TrackRow.youtube_id == youtube_id))
            if track_id is None:
                raise KeyError("track not found")
            return int(track_id)

    def get(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = session.get(TrackRow, track_id)
            if row is None:
                raise KeyError("track not found")
            return track_from_orm(row)

    def list_tracks(
        self,
        *,
        query: str | None = None,
        status: str = "active",
        limit: int = 100,
    ) -> list[Track]:
        statement = select(TrackRow)
        filters = _track_status_filters(status)
        needle = (query or "").strip()
        if needle:
            like = f"%{needle}%"
            filters.append(
                or_(
                    TrackRow.title.ilike(like),
                    TrackRow.channel.ilike(like),
                    TrackRow.youtube_id.ilike(like),
                )
            )
        if filters:
            statement = statement.where(*filters)
        statement = statement.order_by(TrackRow.added_at.desc(), TrackRow.id.desc()).limit(limit)
        with self.db.session() as session:
            rows = session.scalars(statement).all()
            return [track_from_orm(row) for row in rows]

    def stats(self) -> dict[str, int]:
        def count_for(session: Session, status: str) -> int:
            statement = (
                select(func.count()).select_from(TrackRow).where(*_track_status_filters(status))
            )
            return int(session.scalar(statement) or 0)

        with self.db.session() as session:
            return {
                "active": count_for(session, "active"),
                "downloaded": count_for(session, "downloaded"),
                "missing": count_for(session, "missing"),
                "failed": count_for(session, "failed"),
                "inactive": count_for(session, "inactive"),
                "deleted": count_for(session, "deleted"),
                "all": count_for(session, "all"),
            }

    def ban(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = session.get(TrackRow, track_id)
            if row is None:
                raise KeyError("track not found")
            row.is_active = False
            row.deleted_at = datetime.now(UTC)
            session.flush()
            return track_from_orm(row)

    def restore(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = session.get(TrackRow, track_id)
            if row is None:
                raise KeyError("track not found")
            row.is_active = True
            row.deleted_at = None
            session.flush()
            return track_from_orm(row)

    def retry_download(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = session.get(TrackRow, track_id)
            if row is None:
                raise KeyError("track not found")
            row.audio_path = None
            row.cache_state = "none"
            row.cache_hot_until = None
            row.last_prefetch_at = None
            row.fail_count = 0
            session.flush()
            return track_from_orm(row)

    def get_missing_audio(self, limit: int = 100) -> list[Track]:
        # Очередь работы для prefetch: активные треки без аудиофайла.
        with self.db.session() as session:
            rows = session.scalars(
                select(TrackRow)
                .where(
                    TrackRow.deleted_at.is_(None),
                    TrackRow.is_active.is_(True),
                    (TrackRow.audio_path.is_(None)) | (TrackRow.audio_path == ""),
                    (TrackRow.cache_state.is_(None)) | (TrackRow.cache_state == "none"),
                )
                .order_by(
                    TrackRow.last_prefetch_at.is_not(None),
                    TrackRow.last_prefetch_at.asc(),
                    TrackRow.added_at.asc(),
                )
                .limit(limit)
            ).all()
            return [track_from_orm(row) for row in rows]

    def touch_play(self, track_id: int) -> None:
        with self.db.session() as session:
            session.execute(
                update(TrackRow)
                .where(TrackRow.id == track_id)
                .values(last_played_at=func.now(), play_count=TrackRow.play_count + 1)
            )

    def update_cache_state(
        self,
        *,
        track_id: int | None = None,
        youtube_id: str | None = None,
        cache_state: str | None = None,
        cache_hot_until: str | None = None,
        last_prefetch_at: str | None = None,
        fail_count: int | None = None,
    ) -> None:
        # Частичный update: None означает "оставить текущее значение".
        values: dict[str, object] = {}
        if cache_state is not None:
            values["cache_state"] = cache_state
        if cache_hot_until is not None:
            values["cache_hot_until"] = _datetime_value(cache_hot_until)
        if last_prefetch_at is not None:
            values["last_prefetch_at"] = _datetime_value(last_prefetch_at)
        if fail_count is not None:
            values["fail_count"] = fail_count
        if not values:
            self._identifier_filter(track_id=track_id, youtube_id=youtube_id)
            return
        with self.db.session() as session:
            session.execute(
                update(TrackRow)
                .where(self._identifier_filter(track_id=track_id, youtube_id=youtube_id))
                .values(**values)
            )

    def increment_fail_count(self, track_id: int) -> None:
        with self.db.session() as session:
            session.execute(
                update(TrackRow)
                .where(TrackRow.id == track_id)
                .values(
                    fail_count=TrackRow.fail_count + 1,
                    last_prefetch_at=func.now(),
                )
            )

    def update_track_audio(
        self,
        *,
        track_id: int | None = None,
        youtube_id: str | None = None,
        audio_path: str,
        loudness_lufs: float | None = None,
    ) -> None:
        # После успешного скачивания фиксируем путь и сбрасываем счетчик ошибок.
        values: dict[str, object] = {
            "audio_path": audio_path,
            "cache_state": "cold",
            "last_prefetch_at": func.now(),
            "fail_count": 0,
        }
        if loudness_lufs is not None:
            values["loudness_lufs"] = loudness_lufs
        with self.db.session() as session:
            session.execute(
                update(TrackRow)
                .where(self._identifier_filter(track_id=track_id, youtube_id=youtube_id))
                .values(**values)
            )

    def update_track_cached(
        self,
        *,
        track_id: int | None = None,
        youtube_id: str | None = None,
        cache_state: str,
        cache_hot_until: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "cache_state": cache_state,
            "last_prefetch_at": func.now(),
        }
        if cache_hot_until is not None:
            values["cache_hot_until"] = _datetime_value(cache_hot_until)
        with self.db.session() as session:
            session.execute(
                update(TrackRow)
                .where(self._identifier_filter(track_id=track_id, youtube_id=youtube_id))
                .values(**values)
            )

    @staticmethod
    def _identifier_filter(
        *,
        track_id: int | None = None,
        youtube_id: str | None = None,
    ) -> ColumnElement[bool]:
        # Один helper держит SQLAlchemy WHERE одинаковым для обновления по id и youtube_id.
        if track_id is not None:
            return TrackRow.id == track_id
        if youtube_id is not None:
            return TrackRow.youtube_id == youtube_id
        raise ValueError("track_id or youtube_id is required")


def _track_status_filters(status: str) -> list[ColumnElement[bool]]:
    match status:
        case "all":
            return []
        case "active":
            return [TrackRow.deleted_at.is_(None), TrackRow.is_active.is_(True)]
        case "downloaded":
            return [
                TrackRow.deleted_at.is_(None),
                TrackRow.is_active.is_(True),
                TrackRow.audio_path.is_not(None),
                TrackRow.audio_path != "",
            ]
        case "missing":
            return [
                TrackRow.deleted_at.is_(None),
                TrackRow.is_active.is_(True),
                (TrackRow.audio_path.is_(None)) | (TrackRow.audio_path == ""),
                TrackRow.fail_count <= 0,
            ]
        case "failed":
            return [
                TrackRow.deleted_at.is_(None),
                TrackRow.is_active.is_(True),
                TrackRow.fail_count > 0,
            ]
        case "inactive":
            return [TrackRow.deleted_at.is_(None), TrackRow.is_active.is_(False)]
        case "deleted":
            return [TrackRow.deleted_at.is_not(None)]
        case _:
            raise ValueError(f"unknown track status: {status}")


def _datetime_value(value: str) -> datetime:
    # Внешний код хранит даты как ISO-строки, ORM-колонки ожидают datetime.
    normalized = value.removesuffix("Z")
    if normalized != value:
        normalized += "+00:00"
    return datetime.fromisoformat(normalized)


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
            return int(row.id)

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
        # Вставка "следующим" ставит элемент чуть выше текущего top pending.
        step = 0.005
        top = self._get_top_pending_sort_key()
        if top is None:
            playing = self._get_current_playing_sort_key()
            base = playing if playing is not None else 100.0
            new_key = base - step
        else:
            new_key = top - step
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
                .values(status="playing")
            )

    def mark_done(self, queue_id: int, *, skipped: bool = False) -> None:
        status = "skipped" if skipped else "done"
        with self.db.session() as session:
            session.execute(
                update(QueueItemRow).where(QueueItemRow.id == queue_id).values(status=status)
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

    def skip_current(self) -> int:
        # Skip может касаться queued request до старта или уже играющего трека.
        with self.db.session() as session:
            ids = session.scalars(
                select(QueueItemRow.id).where(QueueItemRow.status.in_(("queued", "playing")))
            ).all()
            if not ids:
                return 0
            session.execute(
                update(QueueItemRow).where(QueueItemRow.id.in_(ids)).values(status="skipped")
            )
            return len(ids)

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


@dataclass(frozen=True)
class OffersRepo:
    # Предложка отделена от каталога: принятая заявка может ссылаться на Track,
    # но новый offer сам по себе еще не является треком.
    db: Database

    def add(
        self, youtube_url: str, *, submitted_by: str | None = None, note: str | None = None
    ) -> int:
        with self.db.session() as session:
            row = OfferRow(youtube_url=youtube_url, submitted_by=submitted_by, note=note)
            session.add(row)
            session.flush()
            return int(row.id)

    def get_by_url(self, youtube_url: str) -> Offer | None:
        with self.db.session() as session:
            row = session.scalar(select(OfferRow).where(OfferRow.youtube_url == youtube_url))
            return offer_from_orm(row) if row is not None else None

    def get(self, offer_id: int) -> Offer:
        with self.db.session() as session:
            row = session.get(OfferRow, offer_id)
            if row is None:
                raise KeyError("offer not found")
            return offer_from_orm(row)

    def list(self, *, status: str | None = None, limit: int = 200) -> list[Offer]:
        statement = select(OfferRow).order_by(OfferRow.created_at.desc()).limit(limit)
        if status:
            statement = statement.where(OfferRow.status == status)
        with self.db.session() as session:
            rows = session.scalars(statement).all()
            return [offer_from_orm(row) for row in rows]

    def accept(self, offer_id: int, track_id: int) -> None:
        with self.db.session() as session:
            session.execute(
                update(OfferRow)
                .where(OfferRow.id == offer_id, OfferRow.status == "new")
                .values(status="accepted", accepted_track_id=track_id, processed_at=func.now())
            )

    def cancel(self, offer_id: int) -> None:
        with self.db.session() as session:
            session.execute(
                update(OfferRow)
                .where(OfferRow.id == offer_id, OfferRow.status == "new")
                .values(status="cancelled", processed_at=func.now())
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
        # Метаданные предложки можно дополнять постепенно, не затирая старые поля.
        values = {
            key: value
            for key, value in {
                "youtube_id": youtube_id,
                "title": title,
                "duration_sec": duration_sec,
                "channel": channel,
            }.items()
            if value is not None
        }
        if not values:
            return
        with self.db.session() as session:
            session.execute(update(OfferRow).where(OfferRow.id == offer_id).values(**values))

    def soft_delete(self, track_id: int) -> None:
        TracksRepo(self.db).ban(track_id)

    def restore(self, track_id: int) -> None:
        TracksRepo(self.db).restore(track_id)
