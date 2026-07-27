# retention-lifecycle Specification

## Purpose

TBD - created by archiving change retention-data-lifecycle. Update Purpose after archive.

## Requirements

### Requirement: Safe audio retention

The system SHALL identify removable audio-cache files using configured retention limits while protecting files needed by
active catalog tracks, queued playback, and the currently playing track.

#### Scenario: Protected audio is over the limit

- **WHEN** the cold cache exceeds its configured quota and an old file is referenced by an active or queued track
- **THEN** the retention decision protects that file
- **AND** selects only unprotected files for removal

#### Scenario: Unreferenced audio is over the limit

- **WHEN** the cold cache exceeds its configured quota and an old file is not referenced by protected runtime state
- **THEN** the retention decision selects it before newer unprotected files

### Requirement: Dry-run retention

The system MUST support a dry-run that reports protected, removable, skipped, and failed candidates without deleting
files.

#### Scenario: Dry-run is requested

- **WHEN** retention runs in dry-run mode
- **THEN** it produces a deterministic report of decisions
- **AND** all candidate files remain unchanged

### Requirement: Backup lifecycle

The system SHALL retain the configured newest PostgreSQL backup artifacts and select older recognized dump files for
removal without considering unrelated files.

#### Scenario: Backup retention runs

- **WHEN** the backup directory contains more recognized dumps than the configured retention count
- **THEN** the newest configured number remains
- **AND** older recognized dumps are selected for removal
- **AND** unrelated files remain untouched

#### Scenario: Backup deletion fails

- **WHEN** deletion of one selected backup fails
- **THEN** the report records that failure
- **AND** evaluation continues for the remaining selected backups

### Requirement: Scheduled retention

Production SHALL run retention automatically as a Kubernetes-managed maintenance job after the daily database backup.

#### Scenario: Scheduled cleanup runs

- **WHEN** the retention CronJob starts on its configured schedule
- **THEN** it runs the same protected audio and backup deletion path as the manual `--delete` command
- **AND** it exits with an operator-visible result
- **AND** a concurrent retention run is not started
