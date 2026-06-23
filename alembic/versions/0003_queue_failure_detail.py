from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003_queue_failure_detail"
down_revision: str | None = "0002_queue_runtime"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS queue_visible")
    op.add_column("queue_items", sa.Column("error_detail", sa.Text()))
    op.drop_constraint("ck_queue_items_status", "queue_items", type_="check")
    op.create_check_constraint(
        "ck_queue_items_status",
        "queue_items",
        "status IN ('pending', 'queued', 'playing', 'done', 'skipped', 'failed')",
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION queue_items_status_timestamp()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'playing' AND NEW.started_at IS NULL THEN
                NEW.started_at = now();
            END IF;

            IF NEW.status IN ('done', 'skipped', 'failed') AND NEW.finished_at IS NULL THEN
                NEW.finished_at = now();
            END IF;

            RETURN NEW;
        END;
        $$;
        """)
    op.execute("""
        CREATE VIEW queue_visible AS
        SELECT
            qi.id AS queue_id,
            qi.status,
            qi.error_detail,
            qi.sort_key,
            qi.enqueued_at,
            qi.started_at,
            qi.finished_at,
            t.id AS track_id,
            t.youtube_id,
            t.title,
            t.duration_sec,
            t.url,
            t.channel
        FROM queue_items qi
        JOIN tracks t ON t.id = qi.track_id
        WHERE qi.status IN ('queued', 'playing', 'pending')
          AND t.deleted_at IS NULL;
        """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS queue_visible")
    op.execute("UPDATE queue_items SET status = 'skipped' WHERE status = 'failed'")
    op.drop_constraint("ck_queue_items_status", "queue_items", type_="check")
    op.create_check_constraint(
        "ck_queue_items_status",
        "queue_items",
        "status IN ('pending', 'queued', 'playing', 'done', 'skipped')",
    )
    op.execute("""
        CREATE OR REPLACE FUNCTION queue_items_status_timestamp()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.status = 'playing' AND NEW.started_at IS NULL THEN
                NEW.started_at = now();
            END IF;

            IF NEW.status IN ('done', 'skipped') AND NEW.finished_at IS NULL THEN
                NEW.finished_at = now();
            END IF;

            RETURN NEW;
        END;
        $$;
        """)
    op.drop_column("queue_items", "error_detail")
    op.execute("""
        CREATE VIEW queue_visible AS
        SELECT
            qi.id AS queue_id,
            qi.status,
            qi.sort_key,
            qi.enqueued_at,
            qi.started_at,
            qi.finished_at,
            t.id AS track_id,
            t.youtube_id,
            t.title,
            t.duration_sec,
            t.url,
            t.channel
        FROM queue_items qi
        JOIN tracks t ON t.id = qi.track_id
        WHERE qi.status IN ('queued', 'playing', 'pending')
          AND t.deleted_at IS NULL;
        """)
