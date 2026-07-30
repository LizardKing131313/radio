## Context

The pod contains independent search, prefetch, queue-player, API, Liquidsoap, FFmpeg, and Nginx containers. Existing
readiness probes mostly check PostgreSQL or HTTP availability. The admin app already loads `/api/metrics` but only uses
part of its response.

## Decisions

- Add `manager.health` helpers that atomically write JSON heartbeat files and validate their age.
- Python long-running loops touch their component heartbeat after successful initialization and after each completed
  tick.
- API exposes `/health/live` without database work and `/health/ready` with the existing schema check. Keep `/health` as
  the readiness-compatible route.
- Kubernetes uses heartbeat exec probes for Python workers. Liquidsoap and FFmpeg use conservative liveness checks for
  fresh output; they do not participate in pod readiness because a transient media-output gap must not remove the API
  and admin surface from the Service and cause public 503 responses.
- Add the runtime volume to prefetch. Nginx keeps its existing HTTP probe.
- Admin fetches `/api/metrics` after login and every 15 seconds, showing queue/catalog/HLS/YouTube values without
  exposing new data to unauthenticated clients.

## Failure Behavior

Missing or stale heartbeat/output fails the corresponding probe. API/worker readiness controls service availability;
media-output liveness failures allow Kubernetes to restart the media process without taking the API and admin surface
out of service. Metrics/API failures remain visible as an admin error and do not mutate playback.

## Testing

Cover heartbeat age and atomic writes, health endpoint semantics, probe command outcomes, metrics client typing, and the
admin runtime panel. Run full coverage, frontend checks, pre-commit, strict OpenSpec validation, and kustomize.
