## Why

The application already exposes a Prometheus-compatible endpoint, but it is protected by the browser admin session and
does not expose enough derived health signals for external monitoring. Operators therefore discover HLS, queue,
prefetch, and YouTube failures from logs instead of a stable metric contract.

## What Changes

- Expose a read-only Prometheus scrape surface that does not require an admin browser cookie.
- Add gauges for queue depth, failed/missing tracks, now-playing freshness/audibility, and YouTube API errors.
- Keep metrics derived from existing database and runtime files; do not add a metrics database or a new process.
- Document example alert thresholds and the production scrape path.

## Capabilities

### New Capabilities

- `runtime-monitoring`: Stable operational metrics and scrape behavior for the radio runtime.

### Modified Capabilities

- `api-surface`: The Prometheus endpoint becomes a read-only operational surface that can be scraped without browser
  authentication.

## Impact

- Affected code: FastAPI metrics routes, queue/catalog repositories, and runtime snapshot serialization.
- Affected deployment/docs: scrape path and alert guidance only; no new Kubernetes workload or third-party dependency.
- Validation: focused API/metric tests, full Python CI, OpenSpec validation, and rendered Kubernetes manifests.
