from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from .db import Database
from .models import Track
from .orm import TrackRow, track_from_orm
from .orm_typing import optional_row, orm_int, sql_bool


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
            return orm_int(row.id)

    def get_id_by_youtube_id(self, youtube_id: str) -> int:
        with self.db.session() as session:
            track_id = session.scalar(select(TrackRow.id).where(TrackRow.youtube_id == youtube_id))
            if track_id is None:
                raise KeyError("track not found")
            return int(track_id)

    def get(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = optional_row(session.get(TrackRow, track_id), TrackRow)
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
            row = optional_row(session.get(TrackRow, track_id), TrackRow)
            if row is None:
                raise KeyError("track not found")
            row.is_active = False
            row.deleted_at = datetime.now(UTC)
            session.flush()
            return track_from_orm(row)

    def restore(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = optional_row(session.get(TrackRow, track_id), TrackRow)
            if row is None:
                raise KeyError("track not found")
            row.is_active = True
            row.deleted_at = None
            session.flush()
            return track_from_orm(row)

    def retry_download(self, track_id: int) -> Track:
        with self.db.session() as session:
            row = optional_row(session.get(TrackRow, track_id), TrackRow)
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
        cache_state: str = "cold",
    ) -> None:
        # После успешного скачивания фиксируем путь и сбрасываем счетчик ошибок.
        values: dict[str, object] = {
            "audio_path": audio_path,
            "cache_state": cache_state,
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
        audio_path: str | None = None,
        cache_hot_until: str | None = None,
    ) -> None:
        values: dict[str, object] = {
            "cache_state": cache_state,
            "last_prefetch_at": func.now(),
        }
        if audio_path is not None:
            values["audio_path"] = audio_path
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
            return sql_bool(TrackRow.id == track_id)
        if youtube_id is not None:
            return sql_bool(TrackRow.youtube_id == youtube_id)
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
