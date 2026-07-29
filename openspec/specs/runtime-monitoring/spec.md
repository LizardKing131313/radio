## Purpose

Defines the operational metrics exposed by the radio runtime for external monitoring without adding a monitoring service
to the application deployment.

## Requirements

### Requirement: Runtime metrics are scrapeable

The system SHALL expose a read-only Prometheus exposition endpoint for operational monitoring without requiring a
browser admin session, and SHALL NOT include secrets or user-facing track metadata in that endpoint.

#### Scenario: Monitoring client scrapes metrics

- **WHEN** a client requests `/api/metrics/prometheus`
- **THEN** the API returns HTTP 200 with Prometheus exposition content without an admin cookie
- **AND** the response contains only operational metrics and bounded labels

#### Scenario: JSON metrics remain protected

- **WHEN** an unauthenticated client requests `/api/metrics`
- **THEN** the API continues to require admin authentication

### Requirement: Runtime health signals are exposed

The Prometheus endpoint SHALL expose queue depth, catalog failure/missing counts, nowplaying freshness/audibility, and
YouTube API error/quota gauges using the existing database and runtime state.

#### Scenario: Runtime is healthy

- **WHEN** the queue, nowplaying state, and YouTube telemetry are available
- **THEN** metrics report their current numeric values

#### Scenario: Nowplaying is stale or absent

- **WHEN** Liquidsoap has not written usable nowplaying metadata
- **THEN** the endpoint exposes a safe stale/unknown numeric signal without claiming audio is audible

### Requirement: Monitoring does not mutate runtime state

Metrics collection MUST remain read-only and MUST NOT enqueue, skip, search, download, or alter catalog state.

#### Scenario: Repeated scrapes

- **WHEN** monitoring scrapes the endpoint repeatedly
- **THEN** queue, playback, search, and database mutation state remains unchanged
