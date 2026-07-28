## 1. Tests First

- [x] 1.1 Add tests for live API response normalization, disabled configuration, refresh due-time, and minimum interval.
- [x] 1.2 Add tests for success, not-found/ended, API error, malformed response, and atomic runtime-state fallback.
- [x] 1.3 Add API tests proving `/current` includes live state without changing existing now-playing and queue fields.

## 2. Configuration And Runtime State

- [x] 2.1 Add `youtube_live` configuration defaults, YAML examples, and runtime state path handling.
- [x] 2.2 Implement normalized live metadata state and atomic read/write helpers with stale/error fields.

## 3. Synchronization And API

- [x] 3.1 Implement the single-video YouTube metadata request using the existing API key and telemetry/error patterns.
- [x] 3.2 Add refresh scheduling to the existing search worker without adding a process or changing catalog search
  cadence.
- [x] 3.3 Expose live state through `/current` and preserve disabled/unknown fallback behavior.

## 4. Validation And Deployment

- [x] 4.1 Run `openspec validate --all --strict --no-interactive`.
- [x] 4.2 Run the repository CI checks and resolve all failures, including 100% coverage.
- [x] 4.3 Run `kubectl kustomize deploy` and production smoke checks with live metadata disabled; configured live
  polling is deferred until a real YouTube Live video flow exists.
