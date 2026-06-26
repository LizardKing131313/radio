from __future__ import annotations

from fastapi import FastAPI

from manager.api.dependencies import get_database, lifespan, require_admin_token
from manager.api.routes import (
    queued_play_uri as _queued_play_uri,
    remove_track_files as _remove_track_files,
    router as api_router,
    track_play_now,
)
from manager.api.web import router as web_router, safe_web_path as _safe_web_path

app = FastAPI(title="radio-manager", lifespan=lifespan)
app.include_router(web_router)
app.include_router(api_router)

__all__ = [
    "_queued_play_uri",
    "_remove_track_files",
    "_safe_web_path",
    "app",
    "get_database",
    "require_admin_token",
    "track_play_now",
]
