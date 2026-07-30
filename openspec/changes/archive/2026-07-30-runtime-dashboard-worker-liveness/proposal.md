## Why

Runtime metrics now exist, but the admin panel does not display them and Kubernetes cannot detect workers that remain
running while no longer making progress. Operators need one view of runtime health and probes that distinguish a dead
process from a stale pipeline.

## What Changes

- Add a runtime health section to the admin UI using the protected JSON metrics endpoint.
- Add heartbeat files for Python workers and freshness probes for HLS/nowplaying output.
- Separate API liveness from database readiness and wire Kubernetes probes for all relevant containers.
- Keep existing authentication and avoid new services or dependencies.

## Capabilities

### New Capabilities

- `runtime-dashboard`: Admin-visible runtime statistics and health indicators.
- `worker-liveness`: Progress heartbeats and Kubernetes liveness/readiness behavior.

### Modified Capabilities

- `api-surface`: Add explicit live/ready health endpoints and preserve the protected metrics contract.
- `deployment`: Add component probes and shared runtime health volume wiring.

## Impact

- Affected backend, frontend, and Kubernetes deployment manifests.
- No database migration and no new external service.
- Validation covers Python, frontend, rendered manifests, and production probe behavior.
