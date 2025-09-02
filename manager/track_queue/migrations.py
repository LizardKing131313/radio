# --- Simple SQL migrations (embedded) -----------------------------------------
# Версионирование максимально простое: числовые версии, один файл на версию.
MIGRATIONS: list[tuple[int, str]] = [
    (
        1,
        """
        PRAGMA foreign_keys=ON;

        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     INTEGER PRIMARY KEY,
            applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
        );

        CREATE TABLE IF NOT EXISTS tracks (
            id             INTEGER PRIMARY KEY,
            youtube_id     TEXT NOT NULL UNIQUE,
            title          TEXT NOT NULL,
            duration_sec   INTEGER NOT NULL,
            channel        TEXT,
            url            TEXT NOT NULL,
            thumbnail_url  TEXT,
            audio_path     TEXT,
            loudness_lufs  REAL,
            added_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            last_played_at TEXT,
            play_count     INTEGER NOT NULL DEFAULT 0,
            is_active      INTEGER NOT NULL DEFAULT 1
        );
        CREATE INDEX IF NOT EXISTS idx_tracks_title ON tracks(title);
        CREATE INDEX IF NOT EXISTS idx_tracks_added_at ON tracks(added_at);

        CREATE TABLE IF NOT EXISTS queue_items (
            id           INTEGER PRIMARY KEY,
            track_id     INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','playing','done','skipped')),
            priority     INTEGER NOT NULL DEFAULT 0,
            requested_by TEXT,
            note         TEXT,
            enqueued_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            started_at   TEXT,
            finished_at  TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_queue_pending_order
            ON queue_items(status, priority DESC, enqueued_at ASC);
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);

        CREATE TABLE IF NOT EXISTS offers (
            id                 INTEGER PRIMARY KEY,
            youtube_url        TEXT NOT NULL UNIQUE,
            youtube_id         TEXT,
            title              TEXT,
            duration_sec       INTEGER,
            channel            TEXT,
            submitted_by       TEXT,
            note               TEXT,
            status             TEXT NOT NULL DEFAULT 'new' CHECK (status IN ('new','accepted','cancelled')),
            accepted_track_id  INTEGER,
            created_at         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            processed_at       TEXT,
            FOREIGN KEY (accepted_track_id) REFERENCES tracks(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_offers_status_created
            ON offers(status, created_at DESC);
        """,  # noqa: E501
    ),
    # v2 — anti-spam + sort_key + triggers
    (
        2,
        """
        PRAGMA foreign_keys=ON;

        -- 5) Anti-spam: allow only one 'pending' item per track at a time.
        CREATE UNIQUE INDEX IF NOT EXISTS uq_queue_pending_unique_track
        ON queue_items(track_id)
        WHERE status = 'pending';

        -- 7) Stable ordering key to enable infinite "insert after current" without re-numbering.
        ALTER TABLE queue_items ADD COLUMN sort_key REAL;

        -- Backfill sort_key anchors:
        UPDATE queue_items
           SET sort_key = 100.0
         WHERE status = 'playing' AND sort_key IS NULL;

        CREATE TEMP TABLE q_order(id INTEGER PRIMARY KEY, rn INTEGER);
        INSERT INTO q_order
        SELECT id,
               ROW_NUMBER() OVER (
                 ORDER BY priority DESC, enqueued_at ASC, id ASC
               ) AS rn
          FROM queue_items
         WHERE status = 'pending';

        UPDATE queue_items
           SET sort_key = 100.0 - 0.01 * (SELECT rn FROM q_order WHERE q_order.id = queue_items.id)
         WHERE id IN (SELECT id FROM q_order) AND sort_key IS NULL;

        DROP TABLE q_order;

        -- Helpful index for new ordering:
        CREATE INDEX IF NOT EXISTS idx_queue_status_sort
          ON queue_items(status, sort_key DESC);

        -- 8) Triggers for timestamps.
        CREATE TRIGGER IF NOT EXISTS trg_queue_started
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status = 'playing' AND NEW.started_at IS NULL
        BEGIN
            UPDATE queue_items
               SET started_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_queue_finished
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status IN ('done','skipped') AND NEW.finished_at IS NULL
        BEGIN
            UPDATE queue_items
               SET finished_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;
        """,
    ),
    # v3 — remove 'priority' + default sort_key trigger (RADIO-DB-12, RADIO-DB-13)
    (
        3,
        """
        PRAGMA foreign_keys=ON;

        -- Drop legacy objects referencing 'priority'
        DROP INDEX IF EXISTS idx_queue_pending_order;

        -- Rebuild queue_items without 'priority' (SQLite-safe way).
        -- Keep same columns order except removed 'priority'.
        CREATE TABLE IF NOT EXISTS queue_items_v3 (
            id           INTEGER PRIMARY KEY,
            track_id     INTEGER NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','playing','done','skipped')),
            requested_by TEXT,
            note         TEXT,
            enqueued_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
            started_at   TEXT,
            finished_at  TEXT,
            sort_key     REAL,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        );

        INSERT INTO queue_items_v3 (id, track_id, status, requested_by, note, enqueued_at, started_at, finished_at, sort_key)
        SELECT id, track_id, status, requested_by, note, enqueued_at, started_at, finished_at, sort_key
          FROM queue_items;

        DROP TRIGGER IF EXISTS trg_queue_started;
        DROP TRIGGER IF EXISTS trg_queue_finished;
        DROP TABLE queue_items;

        ALTER TABLE queue_items_v3 RENAME TO queue_items;

        -- Recreate indexes
        CREATE INDEX IF NOT EXISTS idx_queue_status ON queue_items(status);
        CREATE INDEX IF NOT EXISTS idx_queue_status_sort ON queue_items(status, sort_key DESC);

        -- Keep anti-spam unique index
        DROP INDEX IF EXISTS uq_queue_pending_unique_track;
        CREATE UNIQUE INDEX IF NOT EXISTS uq_queue_pending_unique_track
        ON queue_items(track_id) WHERE status = 'pending';

        -- Recreate triggers for timestamps
        CREATE TRIGGER IF NOT EXISTS trg_queue_started
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status = 'playing' AND NEW.started_at IS NULL
        BEGIN
            UPDATE queue_items
               SET started_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_queue_finished
        AFTER UPDATE OF status ON queue_items
        WHEN NEW.status IN ('done','skipped') AND NEW.finished_at IS NULL
        BEGIN
            UPDATE queue_items
               SET finished_at = (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
             WHERE id = NEW.id;
        END;

        -- 13) Default sort_key for INSERT pending when sort_key is NULL:
        -- Use:
        --   max pending sort_key
        --   else latest playing sort_key
        --   else 100.0
        -- Then subtract STEP.
        DROP TRIGGER IF EXISTS trg_queue_default_sort_key;
        CREATE TRIGGER trg_queue_default_sort_key
        AFTER INSERT ON queue_items
        WHEN NEW.status = 'pending' AND NEW.sort_key IS NULL
        BEGIN
            UPDATE queue_items
               SET sort_key = (
                   COALESCE(
                     (SELECT MAX(sort_key) FROM queue_items WHERE status='pending' AND id <> NEW.id),
                     (SELECT sort_key FROM queue_items WHERE status='playing' ORDER BY started_at DESC LIMIT 1),
                     100.0
                   ) - 0.005
               )
             WHERE id = NEW.id;
        END;
        """,  # noqa: E501
    ),
    # v4 — playing uniqueness + soft delete + view + config
    (
        4,
        """
        PRAGMA foreign_keys=ON;

        -- 17) Enforce only one playing row at a time.
        DROP INDEX IF EXISTS uq_queue_single_playing;
        CREATE UNIQUE INDEX uq_queue_single_playing
          ON queue_items(status)
         WHERE status = 'playing';

        -- 18) Soft delete support for tracks.
        ALTER TABLE tracks ADD COLUMN deleted_at TEXT;

        -- 19) Queue view for fast /queue endpoint.
        DROP VIEW IF EXISTS queue_visible;
        CREATE VIEW queue_visible AS
        SELECT qi.id          AS queue_id,
               qi.status      AS status,
               qi.sort_key    AS sort_key,
               qi.enqueued_at AS enqueued_at,
               qi.started_at  AS started_at,
               qi.finished_at AS finished_at,
               t.id           AS track_id,
               t.youtube_id   AS youtube_id,
               t.title        AS title,
               t.duration_sec AS duration_sec,
               t.url          AS url,
               t.channel      AS channel
          FROM queue_items qi
          JOIN tracks t ON t.id = qi.track_id
         WHERE qi.status IN ('playing','pending')
           AND t.deleted_at IS NULL;

        -- 20) Config table for parameters like sort_step.
        CREATE TABLE IF NOT EXISTS config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        INSERT OR IGNORE INTO config (key, value) VALUES ('queue.sort_step', '0.005');
        """,
    ),
    # v5 — cache_state + hot TTL + prefetch telemetry (RADIO-PF-1)
    (
        5,
        """
        PRAGMA foreign_keys=ON;

        -- Add cache state columns to tracks
        ALTER TABLE tracks ADD COLUMN cache_state TEXT CHECK (cache_state IN ('none','cold','hot')) DEFAULT 'none';
        ALTER TABLE tracks ADD COLUMN cache_hot_until TEXT;
        ALTER TABLE tracks ADD COLUMN last_prefetch_at TEXT;
        ALTER TABLE tracks ADD COLUMN fail_count INTEGER NOT NULL DEFAULT 0;

        -- Helpful indexes for prefetch scans
        CREATE INDEX IF NOT EXISTS idx_tracks_cache_state ON tracks(cache_state);
        CREATE INDEX IF NOT EXISTS idx_tracks_hot_until ON tracks(cache_hot_until);
        CREATE INDEX IF NOT EXISTS idx_tracks_last_prefetch ON tracks(last_prefetch_at);
        CREATE INDEX IF NOT EXISTS idx_tracks_audio_path_null ON tracks((audio_path IS NULL));

        -- Optional: normalize cache_state for already downloaded files
        UPDATE tracks
           SET cache_state = CASE
                               WHEN audio_path IS NOT NULL THEN 'cold'
                               ELSE 'none'
                             END
         WHERE cache_state = 'none';
        """,  # noqa: E501
    ),
]
