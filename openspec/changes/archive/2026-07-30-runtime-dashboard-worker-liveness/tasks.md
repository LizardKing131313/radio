## 1. Health Helpers And API

- [x] 1.1 Add heartbeat/output freshness helpers and focused tests.
- [x] 1.2 Add `/health/live` and `/health/ready`, preserving `/health` compatibility.

## 2. Worker And Kubernetes Probes

- [x] 2.1 Add heartbeat updates to search, prefetch, and queue-player loops.
- [x] 2.2 Add probe CLI checks for worker heartbeat, nowplaying, and HLS output.
- [x] 2.3 Wire liveness/readiness probes and runtime volume mounts in the deployment.

## 3. Admin Runtime Dashboard

- [x] 3.1 Extend frontend API types/client for runtime metrics and add periodic refresh.
- [x] 3.2 Render runtime health cards for catalog, queue, HLS/nowplaying, and YouTube API state.
- [x] 3.3 Add frontend tests for runtime metrics display and refresh failure behavior.

## 4. Validation And Acceptance

- [x] 4.1 Run Python 100% coverage, frontend checks, ruff, black, mypy, and pre-commit.
- [x] 4.2 Run strict OpenSpec validation and `kubectl kustomize deploy`.
- [x] 4.3 Deploy and verify admin runtime stats plus intentional stale/dead probe behavior, then archive the change.
