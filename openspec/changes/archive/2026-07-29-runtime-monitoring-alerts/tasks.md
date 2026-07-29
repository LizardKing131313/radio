## 1. Specification And Tests

- [x] 1.1 Add runtime-monitoring and API delta specs for scrape authentication, metric names, and read-only behavior.
- [x] 1.2 Add focused API tests for unauthenticated Prometheus scrape and protected JSON metrics.
- [x] 1.3 Add tests for queue, catalog, nowplaying, and YouTube health metric values and safe unknown behavior.

## 2. Metrics Implementation

- [x] 2.1 Add minimal repository query helpers for queue status counts if existing list methods are insufficient.
- [x] 2.2 Extend Prometheus serialization with queue, prefetch/catalog, HLS freshness/audibility, and YouTube gauges.
- [x] 2.3 Remove browser-session auth only from `/api/metrics/prometheus`; keep JSON metrics protected.

## 3. Operator Documentation

- [x] 3.1 Document the scrape path and example alert thresholds without adding a monitoring service or dependency.

## 4. Validation

- [x] 4.1 Run focused tests, full 100% coverage, ruff, black, mypy, and pre-commit.
- [x] 4.2 Run strict OpenSpec validation and `kubectl kustomize deploy`.
- [x] 4.3 Verify the public scrape and protected JSON metrics in production, then archive the change.
