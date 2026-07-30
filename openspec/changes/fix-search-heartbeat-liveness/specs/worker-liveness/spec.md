## MODIFIED Requirements

### Requirement: Worker progress health

Long-running Python workers SHALL publish a heartbeat after initialization and successful work cycles, and Kubernetes
SHALL be able to fail a probe when the heartbeat is older than its configured threshold. A worker intentionally sleeping
between scheduled work cycles MUST refresh its heartbeat during that sleep.

#### Scenario: Search waits between catalog ticks

- **WHEN** search is idle or in quota backoff before its next scheduled tick
- **THEN** it refreshes its heartbeat periodically
- **AND** Kubernetes does not restart the healthy worker
