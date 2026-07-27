## MODIFIED Requirements

### Requirement: Filesystem artifact ownership

The system SHALL keep audio cache, FIFO/runtime files, HLS output, and PostgreSQL backup artifacts in the filesystem
instead of PostgreSQL or Redis. Retention operations MUST use PostgreSQL metadata only to protect referenced audio and
MUST NOT move filesystem artifacts into domain tables.

#### Scenario: Prefetch downloads audio

- **WHEN** prefetch downloads and normalizes a track
- **THEN** the audio file is written to the configured cache path
- **AND** PostgreSQL stores only metadata and the file path

#### Scenario: Pod runtime data is recreated

- **WHEN** the radio pod is recreated
- **THEN** FIFO, nowplaying, YouTube runtime JSON, and HLS output may be recreated from runtime processes

#### Scenario: Retention reads protected state

- **WHEN** retention evaluates audio candidates
- **THEN** it reads track and playback references from PostgreSQL
- **AND** it deletes or reports only filesystem artifacts under configured retention roots
