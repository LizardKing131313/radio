## ADDED Requirements

### Requirement: Admin runtime dashboard

The authenticated admin UI SHALL display runtime metrics from `/api/metrics` and refresh them periodically without
changing playback or catalog state.

#### Scenario: Runtime metrics are available

- **WHEN** an authenticated admin opens the dashboard
- **THEN** it shows catalog status, queue status, nowplaying age/audibility, HLS state, and YouTube API state

#### Scenario: Metrics refresh fails

- **WHEN** a periodic metrics request fails
- **THEN** the UI preserves the last successful values and shows an error notice
