## ADDED Requirements

### Requirement: Worker progress health

Long-running Python workers SHALL publish a heartbeat after initialization and successful work cycles, and Kubernetes
SHALL be able to fail a probe when the heartbeat is older than its configured threshold.

#### Scenario: Worker is progressing

- **WHEN** a worker completes its initialization or tick
- **THEN** its heartbeat is atomically updated with a current timestamp

#### Scenario: Worker is stuck

- **WHEN** a worker heartbeat exceeds the allowed age
- **THEN** the liveness probe fails so Kubernetes can restart the container

### Requirement: Pipeline output health

Liquidsoap and FFmpeg liveness SHALL be inferred from fresh shared runtime/output files without making transient media
output gaps change the public pod readiness, while Nginx SHALL retain an HTTP probe.

#### Scenario: Audio pipeline is producing output

- **WHEN** nowplaying metadata and HLS output are fresh
- **THEN** their probes succeed

#### Scenario: Audio pipeline stops progressing

- **WHEN** nowplaying or HLS output becomes stale
- **THEN** the corresponding probe fails without changing database state
