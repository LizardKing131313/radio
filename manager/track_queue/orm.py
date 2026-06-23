from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from manager.track_queue.models import Offer, QueueItem, Track

ID_TYPE = BigInteger().with_variant(Integer, "sqlite")


class Base(DeclarativeBase):
    pass


class TrackRow(Base):
    __tablename__ = "tracks"
    __table_args__ = (
        CheckConstraint("duration_sec >= 0", name="ck_tracks_duration_non_negative"),
        CheckConstraint("cache_state IN ('none', 'cold', 'hot')", name="ck_tracks_cache_state"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    youtube_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    duration_sec: Mapped[int] = mapped_column(Integer, nullable=False)
    channel: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    thumbnail_url: Mapped[str | None] = mapped_column(Text)
    audio_path: Mapped[str | None] = mapped_column(Text)
    loudness_lufs: Mapped[float | None] = mapped_column(Float)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    play_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cache_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="none")
    cache_hot_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_prefetch_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fail_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    queue_items: Mapped[list[QueueItemRow]] = relationship(back_populates="track")


class QueueItemRow(Base):
    __tablename__ = "queue_items"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'queued', 'playing', 'done', 'skipped', 'failed')",
            name="ck_queue_items_status",
        ),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    track_id: Mapped[int] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending")
    requested_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sort_key: Mapped[float | None] = mapped_column(Float)

    track: Mapped[TrackRow] = relationship(back_populates="queue_items")


class OfferRow(Base):
    __tablename__ = "offers"
    __table_args__ = (
        CheckConstraint("duration_sec IS NULL OR duration_sec >= 0", name="ck_offers_duration"),
        CheckConstraint("status IN ('new', 'accepted', 'cancelled')", name="ck_offers_status"),
    )

    id: Mapped[int] = mapped_column(ID_TYPE, primary_key=True, autoincrement=True)
    youtube_url: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    youtube_id: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    duration_sec: Mapped[int | None] = mapped_column(Integer)
    channel: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="new")
    accepted_track_id: Mapped[int | None] = mapped_column(
        ForeignKey("tracks.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ConfigRow(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(Text, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


def track_from_orm(row: TrackRow) -> Track:
    return Track(
        id=int(row.id),
        youtube_id=row.youtube_id,
        title=row.title,
        duration_sec=int(row.duration_sec),
        url=row.url,
        channel=row.channel,
        thumbnail_url=row.thumbnail_url,
        audio_path=row.audio_path,
        loudness_lufs=row.loudness_lufs,
        added_at=_text(row.added_at),
        last_played_at=_optional_text(row.last_played_at),
        play_count=int(row.play_count),
        is_active=int(row.is_active),
        deleted_at=_optional_text(row.deleted_at),
        cache_state=row.cache_state,
        cache_hot_until=_optional_text(row.cache_hot_until),
        last_prefetch_at=_optional_text(row.last_prefetch_at),
        fail_count=int(row.fail_count),
    )


def queue_item_from_orm(row: QueueItemRow) -> QueueItem:
    return QueueItem(
        id=int(row.id),
        track_id=int(row.track_id),
        status=row.status,
        enqueued_at=_text(row.enqueued_at),
        requested_by=row.requested_by,
        note=row.note,
        error_detail=row.error_detail,
        started_at=_optional_text(row.started_at),
        finished_at=_optional_text(row.finished_at),
        sort_key=row.sort_key,
    )


def offer_from_orm(row: OfferRow) -> Offer:
    return Offer(
        id=int(row.id),
        youtube_url=row.youtube_url,
        status=row.status,
        created_at=_text(row.created_at),
        youtube_id=row.youtube_id,
        title=row.title,
        duration_sec=row.duration_sec,
        channel=row.channel,
        submitted_by=row.submitted_by,
        note=row.note,
        accepted_track_id=row.accepted_track_id,
        processed_at=_optional_text(row.processed_at),
    )


def _text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _optional_text(value: object | None) -> str | None:
    return None if value is None else _text(value)
