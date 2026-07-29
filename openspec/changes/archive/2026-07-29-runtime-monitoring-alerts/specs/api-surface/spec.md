## MODIFIED Requirements

### Requirement: Health and telemetry endpoints

The API SHALL expose health and metrics endpoints that report runtime state without mutating playback, queue, or search
state. The Prometheus exposition endpoint SHALL be scrapeable without a browser admin session and SHALL expose only
operational metrics.

#### Scenario: Prometheus scrape is unauthenticated

- **WHEN** a monitoring client requests `/api/metrics/prometheus` without an admin cookie
- **THEN** the endpoint returns the operational Prometheus exposition
- **AND** it does not return secrets or track/user-facing metadata

#### Scenario: JSON metrics remain protected

- **WHEN** an unauthenticated client requests `/api/metrics`
- **THEN** the API rejects the request before returning queue or catalog details
