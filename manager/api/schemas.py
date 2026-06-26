from __future__ import annotations

from pydantic import BaseModel, Field


class EnqueueRequest(BaseModel):
    track_id: int = Field(gt=0)
    requested_by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OfferRequest(BaseModel):
    youtube_url: str = Field(min_length=1, max_length=2000)
    submitted_by: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=500)


class OfferAcceptRequest(BaseModel):
    track_id: int = Field(gt=0)
