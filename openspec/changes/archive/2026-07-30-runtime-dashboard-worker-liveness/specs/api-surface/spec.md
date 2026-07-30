## MODIFIED Requirements

### Requirement: Health and telemetry endpoints

The API SHALL expose `/health/live` as a process liveness response without database work and `/health/ready` as a
database/schema readiness response. The existing `/health` route SHALL remain readiness-compatible.

#### Scenario: API process is alive

- **WHEN** a client requests `/api/health/live`
- **THEN** the API returns HTTP 200 without querying PostgreSQL

#### Scenario: API is ready

- **WHEN** a client requests `/api/health/ready`
- **THEN** the API verifies the database schema and returns HTTP 200 only when ready
