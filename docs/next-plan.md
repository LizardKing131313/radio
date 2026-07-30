# Next Plan

## Current State

The radio is deployed and running in production. The public runtime check confirms:

- `/api/health`, `/api/current`, `/player`, and `/admin` return HTTP 200.
- HLS is reachable through the edge.
- The HLS media sequence advanced from `1785107306` to `1785107310` over eight seconds.
- A new origin/edge rollout is not currently required.

## Completed

- Production runtime acceptance checks completed.
- `add-player-pwa-admin-frontend` archived.
- `stabilize-production-runtime` archived.
- `retention-data-lifecycle` implemented, deployed, accepted, and archived.
- YouTube Live metadata synchronization implemented, accepted with live polling disabled, and archived.
- Runtime monitoring implemented, production scrape accepted, and archived.
- Runtime dashboard and worker liveness deployed, accepted, and archived.

## Next OpenSpec Change

There is no required active change. The current admin authentication remains sufficient.

Implementation order:

1. Revisit YouTube Live configured polling only when a real live video flow exists.
2. Optimize search indexing only after a measured performance problem appears.

## Later Backlog

1. YouTube Live configured polling when a real live video flow exists.
2. Search indexing only after a measured performance problem.

Do not add Redis, a message broker, microservices, or custom orchestration without a concrete measured problem and a
separate OpenSpec change.
