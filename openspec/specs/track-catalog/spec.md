## Purpose

Фиксирует поведение catalog repository and admin track actions. Tracks are the
durable catalog entries used by search, prefetch, queue, metrics, and admin API.

## Requirements

### Requirement: Track status filters

Система SHALL expose stable catalog filters for active, downloaded, missing,
failed, inactive, deleted, and all tracks.

#### Scenario: Downloaded tracks requested

- **WHEN** status filter is `downloaded`
- **THEN** repository returns active non-deleted tracks with a non-empty audio path

#### Scenario: Missing tracks requested

- **WHEN** status filter is `missing`
- **THEN** repository returns active non-deleted tracks without audio path and without failures

#### Scenario: Unknown status requested

- **WHEN** API receives an unsupported status filter
- **THEN** repository raises an error and API returns `400`

### Requirement: Admin ban and restore

Система MUST let admin actions soft-ban and restore tracks without deleting the
catalog row.

#### Scenario: Track is banned

- **WHEN** admin bans a track
- **THEN** repository sets `is_active=false` and `deleted_at`
- **AND** API removes matching audio files from hot and cold cache roots

#### Scenario: Track is restored

- **WHEN** admin restores a banned track
- **THEN** repository sets `is_active=true` and clears `deleted_at`

### Requirement: Retry download

Система SHALL allow admin to schedule a track for re-download by clearing cache
metadata.

#### Scenario: Retry is requested

- **WHEN** admin retries a track download
- **THEN** API removes matching hot/cold files
- **AND** repository clears `audio_path`, cache state, prefetch timestamp, and fail count

### Requirement: Play counters

Система SHALL update play timestamp and play count when a track starts through
queue-player or direct play.

#### Scenario: Queued track starts

- **WHEN** queue-player observes Liquidsoap metadata for a queued track
- **THEN** repository increments play count and updates last played time

#### Scenario: Direct play starts

- **WHEN** admin starts a track immediately
- **THEN** API touches the track play metadata after sending Liquidsoap commands

### Requirement: Safe file removal

Система MUST delete audio files only when resolved paths are inside configured
hot or cold cache roots.

#### Scenario: Stored audio path points outside cache

- **WHEN** a track row contains an audio path outside cache roots
- **THEN** admin ban or retry does not unlink that external path
