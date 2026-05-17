from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic.config import Config
from pydantic import SecretStr
from sqlalchemy import create_engine, text

from alembic import command
from manager.config import AppConfig, DatabaseSettings
from manager.track_queue.db import Database, _sqlalchemy_dsn
from manager.track_queue.repo import OffersRepo, QueueRepo, TracksRepo


@pytest.mark.integration
def test_postgres_alembic_repo_roundtrip(monkeypatch: pytest.MonkeyPatch) -> None:
    dsn = os.getenv("RADIO_INTEGRATION_DATABASE_DSN")
    if not dsn:
        pytest.skip("Set RADIO_INTEGRATION_DATABASE_DSN to run PostgreSQL integration test.")

    _reset_public_schema(dsn)
    monkeypatch.setenv("RADIO_DATABASE_DSN", dsn)
    command.upgrade(Config(str(Path("alembic.ini"))), "head")

    database = Database(
        app_config=AppConfig(database=DatabaseSettings(dsn_raw=SecretStr(dsn))),
        dsn=dsn,
    )
    try:
        database.ensure_schema()
        tracks = TracksRepo(database)
        queue = QueueRepo(database)
        offers = OffersRepo(database)

        track_id = tracks.upsert("youtube0001", "Track", 120)
        queue_id = queue.enqueue(track_id, requested_by="integration")
        offer_id = offers.add("https://youtu.be/x")

        assert tracks.get(track_id).youtube_id == "youtube0001"
        next_item = queue.peek_next()
        assert next_item is not None
        assert next_item[0].id == queue_id
        assert offers.get(offer_id).youtube_url == "https://youtu.be/x"
    finally:
        database.close()


def _reset_public_schema(dsn: str) -> None:
    engine = create_engine(_sqlalchemy_dsn(dsn), isolation_level="AUTOCOMMIT")
    try:
        with engine.connect() as connection:
            # CI-БД одноразовая; сброс схемы делает тест независимым от порядка запусков.
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    finally:
        engine.dispose()
