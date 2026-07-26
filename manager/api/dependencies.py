from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hashlib import sha256
from hmac import compare_digest, new
from time import time
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request, status

from manager.config import MissingConfigError, get_settings
from manager.track_queue.db import Database


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    database = Database()
    app.state.database = database
    try:
        yield
    finally:
        database.close()


def get_database(request: Request) -> Database:
    return request.app.state.database


DatabaseDep = Annotated[Database, Depends(get_database)]


ADMIN_SESSION_COOKIE = "radio_admin_session"
ADMIN_SESSION_MAX_AGE = 8 * 60 * 60


def _session_signature(payload: str, secret: str) -> str:
    return new(secret.encode(), payload.encode(), sha256).hexdigest()


def make_admin_session(username: str) -> str:
    settings = get_settings()
    expires = str(int(time()) + ADMIN_SESSION_MAX_AGE)
    payload = f"{username}:{expires}"
    signature = _session_signature(payload, settings.secrets.admin_password.get_secret_value())
    return f"{payload}:{signature}"


def valid_admin_session(value: str | None) -> bool:
    try:
        username, expires, signature = (value or "").split(":", 2)
        settings = get_settings()
        expected = _session_signature(
            f"{username}:{expires}", settings.secrets.admin_password.get_secret_value()
        )
        return (
            compare_digest(username, settings.secrets.admin_username)
            and compare_digest(signature, expected)
            and int(expires) >= int(time())
        )
    except (MissingConfigError, ValueError):
        return False


def require_admin_session(request: Request) -> None:
    if not valid_admin_session(request.cookies.get(ADMIN_SESSION_COOKIE)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="admin authentication required",
            headers={"WWW-Authenticate": "Session"},
        )


def check_admin_credentials(username: str, password: str) -> bool:
    try:
        settings = get_settings()
        return compare_digest(username, settings.secrets.admin_username) and compare_digest(
            password, settings.secrets.admin_password.get_secret_value()
        )
    except MissingConfigError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exception)
        ) from exception
