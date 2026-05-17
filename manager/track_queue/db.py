from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from manager.config import AppConfig, get_settings
from manager.logger import get_logger


class Database:
    """Тонкая обертка над SQLAlchemy engine/session.

    Все DDL живет в Alembic. `ensure_schema()` намеренно остается только
    readiness-check, а не application-side миграцией.
    """

    def __init__(
        self,
        app_config: AppConfig | None = None,
        dsn: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        self._config = app_config or get_settings()
        self._dsn = dsn or self._config.database.dsn.get_secret_value()
        self._engine = engine or create_engine(
            _sqlalchemy_dsn(self._dsn),
            pool_pre_ping=True,
            connect_args=(
                {"connect_timeout": self._config.database.connect_timeout_sec}
                if self._dsn.startswith("postgresql")
                else {}
            ),
        )
        self._sessions = sessionmaker(self._engine, expire_on_commit=False)
        self.logger = get_logger("database")
        self.logger.info("Database initialized", dsn=self._safe_dsn())

    @property
    def engine(self) -> Engine:
        return self._engine

    @contextmanager
    def session(self) -> Iterator[Session]:
        # Один short-lived Session на операцию репозитория. Это проще и
        # безопаснее, чем держать общий Session между воркерами.
        session = self._sessions()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def close(self) -> None:
        self._engine.dispose()

    def ensure_schema(self) -> None:
        # Проверяем именно таблицу tracks как базовый признак примененной схемы.
        try:
            with self.session() as session:
                session.execute(text("SELECT 1 FROM tracks LIMIT 0"))
        except SQLAlchemyError as exception:
            if _looks_like_missing_table(exception):
                raise RuntimeError(
                    "Database schema is not ready. Run Alembic migrations before starting app."
                ) from exception
            raise

    def _safe_dsn(self) -> str:
        # DSN попадает в лог только с замаскированным password.
        try:
            return make_url(_sqlalchemy_dsn(self._dsn)).render_as_string(hide_password=True)
        except Exception:
            return "<invalid dsn>"


def check_database_schema() -> int:
    # CLI/readiness точка входа для Kubernetes probes.
    database = Database()
    database.ensure_schema()
    database.close()
    return 0


def _sqlalchemy_dsn(dsn: str) -> str:
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn.removeprefix("postgresql://")
    return dsn


def _looks_like_missing_table(exception: SQLAlchemyError) -> bool:
    if isinstance(exception, DBAPIError):
        message = str(exception.orig).lower()
    else:
        message = str(exception).lower()
    return "tracks" in message and (
        "does not exist" in message or "undefinedtable" in message or "no such table" in message
    )
