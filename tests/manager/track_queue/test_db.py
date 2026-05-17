from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from manager.config import AppConfig, DatabaseSettings
from manager.track_queue import db as db_module
from manager.track_queue.db import Database
from manager.track_queue.orm import Base


def _config() -> AppConfig:
    return AppConfig(
        database=DatabaseSettings(dsn_raw=SecretStr("postgresql://radio:secret@localhost/radio"))
    )


def test_session_commit_rollback_close_and_safe_dsn() -> None:
    database = Database(app_config=_config(), dsn="sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)

    assert database._safe_dsn() == "sqlite+pysqlite:///:memory:"
    with database.session() as session:
        session.execute(text("INSERT INTO config (key, value) VALUES ('a', 'b')"))

    with database.session() as session:
        assert session.execute(text("SELECT value FROM config WHERE key = 'a'")).scalar_one() == "b"

    with pytest.raises(OperationalError), database.session() as session:
        session.execute(text("SELECT * FROM missing_table"))

    database.close()


def test_safe_dsn_masks_password_and_handles_invalid_value() -> None:
    database = Database(app_config=_config(), dsn="postgresql://radio:secret@localhost/radio")
    assert database._safe_dsn() == "postgresql+psycopg://radio:***@localhost/radio"
    database.close()

    engine = create_engine("sqlite+pysqlite:///:memory:")
    database = Database(app_config=_config(), dsn="not a dsn with spaces", engine=engine)
    assert database._safe_dsn() == "<invalid dsn>"
    database.close()


def test_ensure_schema_and_missing_table_error() -> None:
    database = Database(app_config=_config(), dsn="sqlite+pysqlite:///:memory:")
    with pytest.raises(RuntimeError, match="Alembic"):
        database.ensure_schema()

    Base.metadata.create_all(database.engine)
    database.ensure_schema()


def test_ensure_schema_reraises_unexpected_sqlalchemy_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BrokenSession:
        def execute(self, _statement: object) -> None:
            raise SQLAlchemyError("network is down")

    @contextmanager
    def broken_session() -> Iterator[BrokenSession]:
        yield BrokenSession()

    database = Database(app_config=_config(), dsn="sqlite+pysqlite:///:memory:")
    monkeypatch.setattr(database, "session", broken_session)

    with pytest.raises(SQLAlchemyError, match="network is down"):
        database.ensure_schema()

    database.close()


def test_check_database_schema(monkeypatch: pytest.MonkeyPatch) -> None:
    database = Database(app_config=_config(), dsn="sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(database.engine)
    monkeypatch.setattr(db_module, "Database", lambda: database)

    assert db_module.check_database_schema() == 0


def test_sqlalchemy_dsn_normalizes_postgres_url() -> None:
    assert (
        db_module._sqlalchemy_dsn("postgresql://radio:secret@localhost/radio")
        == "postgresql+psycopg://radio:secret@localhost/radio"
    )
    assert db_module._sqlalchemy_dsn("sqlite+pysqlite:///:memory:") == "sqlite+pysqlite:///:memory:"


def test_missing_table_matcher_accepts_plain_sqlalchemy_error() -> None:
    assert db_module._looks_like_missing_table(SQLAlchemyError("tracks does not exist"))
