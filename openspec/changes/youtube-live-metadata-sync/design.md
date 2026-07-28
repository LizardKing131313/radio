## Context

The existing search worker already owns YouTube Data API access and has a periodic loop, while the API reads ephemeral
runtime JSON for telemetry and now-playing state. The project has no YouTube Live push path and must not acquire stream
keys or add RTMP configuration for metadata-only synchronization.

## Goals / Non-Goals

**Goals:**

- Poll one explicitly configured YouTube video ID at a bounded interval.
- Reuse the search worker's API key and lifecycle rather than adding a new process.
- Write atomic runtime JSON containing status, title, channel, scheduled/start/end times, and last error state.
- Return a stable response when the feature is disabled, unavailable, stale, or successful.

**Non-Goals:**

- No YouTube Live creation, RTMP ingest, stream-key storage, or stream publishing.
- No database schema, queue, Liquidsoap, FFmpeg, HLS, or cache changes.
- No arbitrary live-stream discovery; configuration must identify the source video.

## Decisions

- Add a small `youtube_live` configuration section with `video_id`, `refresh_sec`, and runtime state path. An empty ID
  disables polling and returns an explicit disabled state.
- Extend the existing search loop with a separate due-time check so live metadata refresh cadence is independent from
  the six-hour catalog search interval while remaining in the same Kubernetes container.
- Use `videos.list(part=snippet,liveStreamingDetails,status)` for one ID and normalize only stable fields. Treat
  missing, private, ended, and API-error responses as states rather than exceptions escaping the search loop.
- Write runtime state with the existing atomic JSON pattern. API reads the file and returns an empty/unknown state when
  it is missing or invalid, preserving current endpoint availability.

## Risks / Trade-offs

- [Risk] The configured video ends or changes. -> Report `ended`/`not_found` and require an explicit config update; do
  not guess a replacement stream.
- [Risk] Polling consumes YouTube quota. -> Poll one ID with a configurable minimum interval and reuse existing error
  backoff/telemetry patterns.
- [Risk] Runtime JSON becomes stale during API failure. -> Include `updated_at`, `last_success_at`, and error fields so
  clients can distinguish stale data from a current success.

## Migration Plan

1. Deploy with an empty video ID; behavior remains disabled and backward compatible.
2. Set the video ID and refresh interval in runtime config, then roll out.
3. Verify `/current` and `/health` show successful live metadata refresh.
4. Disable by clearing the video ID; no data migration or rollback step is required.
