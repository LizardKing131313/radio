from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_queue_runtime"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # queued - трек уже передан в Liquidsoap request.queue, но еще может ждать
    # окончания текущего library-трека.
    op.execute("DROP VIEW IF EXISTS queue_visible")
    op.drop_index("uq_queue_pending_unique_track", table_name="queue_items")
    op.drop_constraint("ck_queue_items_status", "queue_items", type_="check")
    op.create_check_constraint(
        "ck_queue_items_status",
        "queue_items",
        "status IN ('pending', 'queued', 'playing', 'done', 'skipped')",
    )
    op.create_index(
        "uq_queue_pending_unique_track",
        "queue_items",
        ["track_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'queued')"),
    )
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


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS queue_visible")
    op.drop_index("uq_queue_pending_unique_track", table_name="queue_items")
    op.execute("UPDATE queue_items SET status = 'pending' WHERE status = 'queued'")
    op.drop_constraint("ck_queue_items_status", "queue_items", type_="check")
    op.create_check_constraint(
        "ck_queue_items_status",
        "queue_items",
        "status IN ('pending', 'playing', 'done', 'skipped')",
    )
    op.create_index(
        "uq_queue_pending_unique_track",
        "queue_items",
        ["track_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
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
        WHERE qi.status IN ('playing', 'pending')
          AND t.deleted_at IS NULL;
        """)
