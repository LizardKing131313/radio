from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from hmac import compare_digest
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status

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


def require_admin_token(authorization: str | None = Header(default=None)) -> None:
    # Мутации закрыты одним token из Kubernetes Secret. Сложнее auth добавим,
    # когда появится реальная внешняя админка.
    try:
        expected = get_settings().secrets.admin_token.get_secret_value()
    except MissingConfigError as exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="admin token is not configured",
        ) from exception

    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid admin token",
            headers={"WWW-Authenticate": "Bearer"},
        )
