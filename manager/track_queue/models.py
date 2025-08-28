from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, TypedDict


# В моделях только структуры данных и конвертация из sqlite Row/Mapping.


class TrackDict(TypedDict, total=False):
    id: int
    youtube_id: str
    title: str
    duration_sec: int
    channel: str | None
    url: str
    thumbnail_url: str | None
    audio_path: str | None
    loudness_lufs: float | None
    added_at: str
    last_played_at: str | None
    play_count: int
    is_active: int
    deleted_at: str | None


class QueueItemDict(TypedDict, total=False):
    id: int
    track_id: int
    status: str
    requested_by: str | None
    note: str | None
    enqueued_at: str
    started_at: str | None
    finished_at: str | None
    sort_key: float | None


class OfferDict(TypedDict, total=False):
    id: int
    youtube_url: str
    youtube_id: str | None
    title: str | None
    duration_sec: int | None
    channel: str | None
    submitted_by: str | None
    note: str | None
    status: str
    accepted_track_id: int | None
    created_at: str
    processed_at: str | None


@dataclass(frozen=True)
class Track:
    id: int
    youtube_id: str
    title: str
    duration_sec: int
    url: str
    channel: str | None = None
    thumbnail_url: str | None = None
    audio_path: str | None = None
    loudness_lufs: float | None = None
    added_at: str = ""
    last_played_at: str | None = None
    play_count: int = 0
    is_active: int = 1
    deleted_at: str | None = None

    @staticmethod
    def from_row(row: Mapping[str, Any]) -> Track:
        return Track(
            id=int(row["id"]),
            youtube_id=str(row["youtube_id"]),
            title=str(row["title"]),
            duration_sec=int(row["duration_sec"]),
            url=str(row["url"]),
            channel=(str(row["channel"]) if row["channel"] is not None else None),
            thumbnail_url=(str(row["thumbnail_url"]) if row["thumbnail_url"] is not None else None),
            audio_path=(str(row["audio_path"]) if row["audio_path"] is not None else None),
            loudness_lufs=(
                float(row["loudness_lufs"]) if row["loudness_lufs"] is not None else None
            ),
            added_at=str(row["added_at"]),
            last_played_at=(
                str(row["last_played_at"]) if row["last_played_at"] is not None else None
            ),
            play_count=int(row["play_count"]),
            is_active=int(row["is_active"]),
            deleted_at=(
                str(row["deleted_at"])
                if "deleted_at" in row and row["deleted_at"] is not None
                else None
            ),
        )

    def to_dict(self) -> TrackDict:
        return TrackDict(
            id=self.id,
            youtube_id=self.youtube_id,
            title=self.title,
            duration_sec=self.duration_sec,
            channel=self.channel,
            url=self.url,
            thumbnail_url=self.thumbnail_url,
            audio_path=self.audio_path,
            loudness_lufs=self.loudness_lufs,
            added_at=self.added_at,
            last_played_at=self.last_played_at,
            play_count=self.play_count,
            is_active=self.is_active,
            deleted_at=self.deleted_at,
        )


@dataclass(frozen=True)
class QueueItem:
    id: int
    track_id: int
    status: str
    enqueued_at: str
    requested_by: str | None = None
    note: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    sort_key: float | None = None

    @staticmethod
    def from_row(row: Mapping[str, Any]) -> QueueItem:
        return QueueItem(
            id=int(row["id"]),
            track_id=int(row["track_id"]),
            status=str(row["status"]),
            enqueued_at=str(row["enqueued_at"]),
            requested_by=(str(row["requested_by"]) if row["requested_by"] is not None else None),
            note=(str(row["note"]) if row["note"] is not None else None),
            started_at=(str(row["started_at"]) if row["started_at"] is not None else None),
            finished_at=(str(row["finished_at"]) if row["finished_at"] is not None else None),
            sort_key=(float(row["sort_key"]) if row["sort_key"] is not None else None),
        )

    def to_dict(self) -> QueueItemDict:
        return QueueItemDict(
            id=self.id,
            track_id=self.track_id,
            status=self.status,
            requested_by=self.requested_by,
            note=self.note,
            enqueued_at=self.enqueued_at,
            started_at=self.started_at,
            finished_at=self.finished_at,
            sort_key=self.sort_key,
        )


@dataclass(frozen=True)
class Offer:
    id: int
    youtube_url: str
    status: str
    created_at: str
    youtube_id: str | None = None
    title: str | None = None
    duration_sec: int | None = None
    channel: str | None = None
    submitted_by: str | None = None
    note: str | None = None
    accepted_track_id: int | None = None
    processed_at: str | None = None

    @staticmethod
    def from_row(row: Mapping[str, Any]) -> Offer:
        return Offer(
            id=int(row["id"]),
            youtube_url=str(row["youtube_url"]),
            status=str(row["status"]),
            created_at=str(row["created_at"]),
            youtube_id=(str(row["youtube_id"]) if row["youtube_id"] is not None else None),
            title=(str(row["title"]) if row["title"] is not None else None),
            duration_sec=(int(row["duration_sec"]) if row["duration_sec"] is not None else None),
            channel=(str(row["channel"]) if row["channel"] is not None else None),
            submitted_by=(str(row["submitted_by"]) if row["submitted_by"] is not None else None),
            note=(str(row["note"]) if row["note"] is not None else None),
            accepted_track_id=(
                int(row["accepted_track_id"]) if row["accepted_track_id"] is not None else None
            ),
            processed_at=(str(row["processed_at"]) if row["processed_at"] is not None else None),
        )

    def to_dict(self) -> OfferDict:
        return OfferDict(
            id=self.id,
            youtube_url=self.youtube_url,
            youtube_id=self.youtube_id,
            title=self.title,
            duration_sec=self.duration_sec,
            channel=self.channel,
            submitted_by=self.submitted_by,
            note=self.note,
            status=self.status,
            accepted_track_id=self.accepted_track_id,
            created_at=self.created_at,
            processed_at=self.processed_at,
        )
