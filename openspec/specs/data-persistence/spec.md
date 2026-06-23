## Purpose

Defines where durable and ephemeral state lives. The project uses PostgreSQL for
domain data, Alembic for schema ownership, Kubernetes Secret for secrets, and the
filesystem for audio/runtime/HLS artifacts.

## Requirements

### Requirement: PostgreSQL domain ownership

The system SHALL store durable domain entities in PostgreSQL when integrity,
querying, or recovery matters.

#### Scenario: Track catalog update

- **WHEN** search discovers or refreshes a track
- **THEN** the track metadata is persisted through the PostgreSQL repository

#### Scenario: Queue state transition

- **WHEN** a queue entry moves from pending to queued, playing, done, or failed
- **THEN** the transition is stored in PostgreSQL

### Requirement: Alembic schema ownership

Database schema changes MUST be represented as Alembic migrations and applied by
the migration job before application containers depend on the new schema.

#### Scenario: New table or column

- **WHEN** a change needs a new persistent field or relation
- **THEN** the change includes an Alembic revision and tests covering the migrated schema

### Requirement: Filesystem artifact ownership

The system SHALL keep audio cache, FIFO/runtime files, and HLS output in the
filesystem instead of PostgreSQL or Redis.

#### Scenario: Prefetch downloads audio

- **WHEN** prefetch downloads and normalizes a track
- **THEN** the audio file is written to the configured cache path
- **AND** PostgreSQL stores only metadata and the file path

#### Scenario: Pod runtime data is recreated

- **WHEN** the radio pod is recreated
- **THEN** FIFO, nowplaying, YouTube runtime JSON, and HLS output may be recreated from runtime processes

### Requirement: Secrets stay out of git

Production secrets MUST live in Kubernetes Secret manifests or cluster secret
storage that is not committed to the repository.

#### Scenario: Local secret file exists

- **WHEN** `deploy/k8s/secret.yaml` is created for local deployment
- **THEN** git ignores it
- **AND** only `deploy/k8s/secret.example.yaml` remains committed
