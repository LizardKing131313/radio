from __future__ import annotations

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from manager.track_queue.db import _sqlalchemy_dsn
from manager.track_queue.orm import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    # Kubernetes передает RADIO_DATABASE_DSN, локально удобнее DATABASE_URL.
    raw = os.getenv("RADIO_DATABASE_DSN") or os.getenv("DATABASE_URL") or os.getenv("POSTGRES_DSN")
    if not raw:
        raise RuntimeError("Set RADIO_DATABASE_DSN, DATABASE_URL or POSTGRES_DSN for Alembic.")
    return _sqlalchemy_dsn(raw)


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Alembic сам открывает короткое подключение и закрывает его после миграций.
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
