## MODIFIED Requirements

### Requirement: Kubernetes probes reflect component health

The deployment SHALL configure liveness/readiness probes for API, Python workers, Liquidsoap, FFmpeg, and Nginx using
process progress, database readiness, or fresh pipeline output as appropriate.

#### Scenario: Worker process is alive but stale

- **WHEN** a Python worker stops updating its heartbeat
- **THEN** its liveness probe fails and Kubernetes can restart that container

#### Scenario: API database is unavailable

- **WHEN** API HTTP is alive but database schema access fails
- **THEN** readiness fails while the liveness endpoint remains available
