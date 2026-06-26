from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select, update

from .db import Database
from .models import Offer
from .orm import OfferRow, offer_from_orm
from .orm_typing import optional_row, orm_int, sql_bool
from .tracks_repo import TracksRepo


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
            return orm_int(row.id)

    def get_by_url(self, youtube_url: str) -> Offer | None:
        with self.db.session() as session:
            row = session.scalar(select(OfferRow).where(OfferRow.youtube_url == youtube_url))
            return offer_from_orm(row) if row is not None else None

    def get(self, offer_id: int) -> Offer:
        with self.db.session() as session:
            row = optional_row(session.get(OfferRow, offer_id), OfferRow)
            if row is None:
                raise KeyError("offer not found")
            return offer_from_orm(row)

    def list(self, *, status: str | None = None, limit: int = 200) -> list[Offer]:
        statement = select(OfferRow).order_by(OfferRow.created_at.desc()).limit(limit)
        if status:
            statement = statement.where(sql_bool(OfferRow.status == status))
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
