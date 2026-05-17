from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op


revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Приложение больше не создает таблицы на старте: схема фиксируется здесь.
    op.create_table(
        "tracks",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("youtube_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("duration_sec", sa.Integer(), nullable=False),
        sa.Column("channel", sa.Text()),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text()),
        sa.Column("audio_path", sa.Text()),
        sa.Column("loudness_lufs", sa.Float()),
        sa.Column(
            "added_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_played_at", sa.DateTime(timezone=True)),
        sa.Column("play_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("cache_state", sa.Text(), nullable=False, server_default="none"),
        sa.Column("cache_hot_until", sa.DateTime(timezone=True)),
        sa.Column("last_prefetch_at", sa.DateTime(timezone=True)),
        sa.Column("fail_count", sa.Integer(), nullable=False, server_default="0"),
        sa.CheckConstraint("duration_sec >= 0", name="ck_tracks_duration_non_negative"),
        sa.CheckConstraint(
            "cache_state IN ('none', 'cold', 'hot')",
            name="ck_tracks_cache_state",
        ),
        sa.UniqueConstraint("youtube_id", name="uq_tracks_youtube_id"),
    )
    # Сложные индексы проще оставить обычным PostgreSQL SQL, без лишней обвязки.
    op.execute("CREATE INDEX idx_tracks_title ON tracks USING gin (to_tsvector('simple', title))")
    op.create_index("idx_tracks_added_at", "tracks", ["added_at"])
    op.create_index("idx_tracks_cache_state", "tracks", ["cache_state"])
    op.create_index("idx_tracks_hot_until", "tracks", ["cache_hot_until"])
    op.create_index("idx_tracks_last_prefetch", "tracks", ["last_prefetch_at"])
    op.execute("CREATE INDEX idx_tracks_audio_path_missing ON tracks ((audio_path IS NULL))")

    op.create_table(
        "queue_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "track_id",
            sa.BigInteger(),
            sa.ForeignKey("tracks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column(
            "enqueued_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("sort_key", sa.Float()),
        sa.CheckConstraint(
            "status IN ('pending', 'playing', 'done', 'skipped')",
            name="ck_queue_items_status",
        ),
    )
    op.create_index("idx_queue_status", "queue_items", ["status"])
    op.execute(
        "CREATE INDEX idx_queue_status_sort ON queue_items (status, sort_key DESC NULLS LAST)"
    )
    op.create_index(
        "uq_queue_pending_unique_track",
        "queue_items",
        ["track_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_queue_single_playing",
        "queue_items",
        ["status"],
        unique=True,
        postgresql_where=sa.text("status = 'playing'"),
    )

    op.create_table(
        "offers",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("youtube_url", sa.Text(), nullable=False),
        sa.Column("youtube_id", sa.Text()),
        sa.Column("title", sa.Text()),
        sa.Column("duration_sec", sa.Integer()),
        sa.Column("channel", sa.Text()),
        sa.Column("submitted_by", sa.Text()),
        sa.Column("note", sa.Text()),
        sa.Column("status", sa.Text(), nullable=False, server_default="new"),
        sa.Column(
            "accepted_track_id",
            sa.BigInteger(),
            sa.ForeignKey("tracks.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "duration_sec IS NULL OR duration_sec >= 0",
            name="ck_offers_duration",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'accepted', 'cancelled')",
            name="ck_offers_status",
        ),
        sa.UniqueConstraint("youtube_url", name="uq_offers_youtube_url"),
    )
    op.execute("CREATE INDEX idx_offers_status_created ON offers (status, created_at DESC)")

    op.create_table(
        "config",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
    )
    op.execute("INSERT INTO config (key, value) VALUES ('queue.sort_step', '0.005')")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION queue_items_default_sort_key()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            next_sort_key DOUBLE PRECISION;
        BEGIN
            IF NEW.status = 'pending' AND NEW.sort_key IS NULL THEN
                SELECT COALESCE(
                    (SELECT MAX(sort_key) FROM queue_items WHERE status = 'pending'),
                    (
                        SELECT sort_key
                        FROM queue_items
                        WHERE status = 'playing'
                        ORDER BY started_at DESC NULLS LAST
                        LIMIT 1
                    ),
                    100.0
                ) - 0.005
                INTO next_sort_key;

                NEW.sort_key = next_sort_key;
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_queue_default_sort_key
        BEFORE INSERT ON queue_items
        FOR EACH ROW
        EXECUTE FUNCTION queue_items_default_sort_key();
        """
    )

    op.execute(
        """
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
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_queue_status_timestamp
        BEFORE UPDATE OF status ON queue_items
        FOR EACH ROW
        EXECUTE FUNCTION queue_items_status_timestamp();
        """
    )

    op.execute(
        """
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
        """
    )


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS queue_visible")
    op.execute("DROP TRIGGER IF EXISTS trg_queue_status_timestamp ON queue_items")
    op.execute("DROP FUNCTION IF EXISTS queue_items_status_timestamp()")
    op.execute("DROP TRIGGER IF EXISTS trg_queue_default_sort_key ON queue_items")
    op.execute("DROP FUNCTION IF EXISTS queue_items_default_sort_key()")
    op.drop_table("config")
    op.drop_table("offers")
    op.drop_table("queue_items")
    op.drop_table("tracks")
