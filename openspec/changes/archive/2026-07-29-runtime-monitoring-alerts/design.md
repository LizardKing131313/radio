## Context

The manager already reads PostgreSQL queue/catalog state, Liquidsoap nowplaying files, HLS timing configuration, and
YouTube API telemetry. `/api/metrics/prometheus` already formats a small set of gauges but currently requires the admin
session dependency.

## Decision

Keep one metrics snapshot and extend its Prometheus serialization. The endpoint will remain read-only and will expose
only numeric gauges and bounded status labels, not titles, URLs, tokens, or queue history. Remove browser-session auth
from the Prometheus route because scrape clients do not have the admin cookie; the JSON `/api/metrics` endpoint remains
admin-protected.

Add repository helpers for queue status counts and failed/missing catalog counts only where the existing repository
queries cannot provide the values without loading large lists. Derive nowplaying age and probable audibility from the
existing `current_snapshot` result.

Metrics include:

- `radio_queue_items{status}` for pending, queued, and playing items;
- `radio_tracks_total{status}` for existing catalog statuses;
- `radio_hls_nowplaying_age_seconds` and `radio_hls_is_probably_audible`;
- `radio_youtube_consecutive_errors`, `radio_youtube_quota_exhausted`, and estimated quota units.

No alert manager, dashboard, dependency, database table, or Kubernetes sidecar is introduced. Alert rules stay operator
documentation because the repository has no Prometheus installation to own them.

## Failure Handling

Missing runtime files produce the existing unknown snapshot and numeric zero/omitted-safe gauges. Database or route
failures continue to use the existing API error behavior rather than silently publishing a false healthy metric.

## Testing

Extend API tests to verify the unauthenticated scrape contract, queue/status gauges, and stale nowplaying values. Run
the existing full coverage gate, pre-commit, strict OpenSpec validation, and `kubectl kustomize deploy`.
