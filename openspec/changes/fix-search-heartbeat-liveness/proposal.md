## Why

The search worker sleeps for hours between catalog API ticks, but its Kubernetes heartbeat was only refreshed after a
tick. The liveness probe therefore restarted a healthy idle worker and briefly removed the pod from service, causing
503s.

## What Changes

- Refresh the search heartbeat during long idle and quota-backoff sleeps.
- Keep the existing search cadence and YouTube quota behavior unchanged.
- Add regression coverage for the heartbeat/liveness contract.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `worker-liveness`: A healthy idle search worker remains live while waiting for its next scheduled tick.

## Impact

Only the search loop and its liveness regression tests change. No API, database, deployment, or dependency changes are
required.
