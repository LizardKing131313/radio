# Next Plan

## Current State

The radio is deployed and running in production. The public runtime check confirms:

- `/api/health`, `/api/current`, `/player`, and `/admin` return HTTP 200.
- HLS is reachable through the edge.
- The HLS media sequence advanced from `1785107306` to `1785107310` over eight seconds.
- A new origin/edge rollout is not currently required.

## Immediate Actions

1. Run a controlled operational acceptance check:

- restart FFmpeg and verify HLS recovery;
- restart prefetch and verify the Node.js/yt-dlp runtime;
- verify manual queue insertion and playback state transitions;
- create a PostgreSQL backup and verify the dump;
- verify that production secrets are not tracked by Git.

2. Record the results in the production runtime change notes or runtime documentation.
3. Archive the completed OpenSpec changes:

- `add-player-pwa-admin-frontend`;
- `stabilize-production-runtime`.

## Next OpenSpec Change

The next recommended change is **retention and data lifecycle**.

Goals:

- prevent unbounded growth of `cache/cold`;
- define safe deletion of old audio files;
- preserve tracks referenced by the queue or current playback;
- define PostgreSQL backup retention;
- add dry-run behavior and tests for deletion decisions;
- avoid API, Liquidsoap, Kubernetes topology, and schema changes unless required.

Implementation order:

1. Create the OpenSpec proposal, spec delta, design, and tasks.
2. Add tests for file selection and protection of active tracks.
3. Implement the smallest retention path.
4. Validate against local and production-like cache data.
5. Run `make ci` and perform a controlled deployment.
6. Verify free disk space and that playable or active tracks were not removed.

## Later Backlog

1. YouTube Live metadata synchronization.
2. Monitoring integration for the existing `/api/metrics/prometheus` endpoint.
3. Stronger admin authentication if the admin panel becomes publicly exposed.
4. Search indexing only after a measured performance problem.

Do not add Redis, a message broker, microservices, or custom orchestration without a concrete measured problem and a
separate OpenSpec change.
