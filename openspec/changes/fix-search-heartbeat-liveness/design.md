## Decision

Keep the existing `search.interval_sec` and quota backoff values. Replace one long `asyncio.sleep` after each search
tick with 30-second sleep slices; after every slice, atomically update the existing search heartbeat file. Apply the
same heartbeat behavior to startup telemetry delay, which may also be long.

This keeps Kubernetes liveness independent from YouTube search cadence without creating another process or changing API
behavior.

## Validation

Run full Python coverage, lint/type checks, pre-commit, strict OpenSpec validation, kustomize, then deploy and verify
the search restart count remains stable for longer than the liveness threshold.
