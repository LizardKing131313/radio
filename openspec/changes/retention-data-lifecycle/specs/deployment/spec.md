## ADDED Requirements

### Requirement: Scheduled retention workload

The Kubernetes deployment SHALL include a dedicated CronJob for retention that uses the production application image,
the PostgreSQL Secret, the radio config ConfigMap, and the existing cache PVC.

#### Scenario: Retention CronJob is rendered

- **WHEN** `kubectl kustomize deploy` renders the manifests
- **THEN** a retention CronJob is present with `concurrencyPolicy: Forbid`
- **AND** its command runs `python -m manager retention --delete`
- **AND** it mounts the cache PVC and can reach PostgreSQL
