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

## Next OpenSpec Change

The next recommended change is **stronger admin authentication**, if the admin panel remains publicly exposed.

Goals:

- define how live stream metadata is discovered and refreshed;
- expose the metadata through the existing now-playing/runtime path;
- preserve the current queue and HLS pipeline;
- avoid RTMP push or stream-key configuration until an actual live push flow exists.

Implementation order:

1. Decide whether the public admin panel needs stronger authentication than the current configured password/session.
2. If yes, create a separate OpenSpec change for the authentication boundary and rollout.
3. Revisit YouTube Live configured polling only when a real live video flow exists.

## Later Backlog

1. YouTube Live metadata synchronization.
2. Monitoring integration for the existing `/api/metrics/prometheus` endpoint.
3. Stronger admin authentication if the admin panel becomes publicly exposed.
4. Search indexing only after a measured performance problem.

Do not add Redis, a message broker, microservices, or custom orchestration without a concrete measured problem and a
separate OpenSpec change.
