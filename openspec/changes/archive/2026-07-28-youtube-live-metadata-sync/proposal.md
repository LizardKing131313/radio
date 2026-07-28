## Why

The radio currently exposes only Liquidsoap's local now-playing metadata. A configured YouTube Live source cannot be
observed through the existing runtime/API surface, so operators and clients have no reliable external live-broadcast
state. The change adds metadata synchronization without introducing an RTMP publisher or stream-key handling.

## What Changes

- Poll YouTube Data API metadata for an explicitly configured live video ID.
- Persist the latest live metadata and error state in the existing ephemeral runtime-info filesystem.
- Expose that state through the existing current/health runtime response without changing HLS or queue behavior.
- Use a bounded refresh interval, atomic state writes, and stale/error fallback behavior.
- Keep the feature disabled when no live video ID is configured.

## Capabilities

### New Capabilities

- `youtube-live-metadata`: Refresh and expose configured YouTube Live metadata with safe fallback behavior.

### Modified Capabilities

- `api-surface`: Include live metadata state in existing runtime responses.
- `app-configuration`: Add non-secret live video ID, refresh interval, and runtime state path configuration.

## Impact

- Affected code: YouTube API client helpers, search worker scheduling, runtime state serialization, API response
  assembly, configuration, and tests.
- Affected deployment: no new process, service, RTMP path, stream key, database table, or Kubernetes topology.
- Validation: focused parser/scheduler/API tests, OpenSpec validation, full CI, and production smoke checks with the
  feature both configured and disabled.
