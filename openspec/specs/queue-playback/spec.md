## Purpose

Defines how manual queue entries become audible playback. PostgreSQL is the
source of truth for queue state, while Liquidsoap request.queue is the playback
integration point.

## Requirements

### Requirement: Queue state synchronization

The queue-player worker SHALL synchronize PostgreSQL queue entries with
Liquidsoap request.queue metadata.

#### Scenario: Pending entry is queued

- **WHEN** a pending queue entry references a playable audio file
- **THEN** queue-player marks it queued and pushes the URI to Liquidsoap request.queue

#### Scenario: Liquidsoap starts queued entry

- **WHEN** Liquidsoap writes nowplaying metadata with the queued entry identifier
- **THEN** queue-player marks the matching PostgreSQL entry as playing

#### Scenario: Liquidsoap returns to library playback

- **WHEN** nowplaying metadata no longer references the active queue entry
- **THEN** queue-player marks the entry done if playback completed successfully

### Requirement: Queue failure visibility

Queue playback failures MUST be persisted in PostgreSQL instead of being hidden
in logs only.

#### Scenario: Missing audio file

- **WHEN** a queue entry points to an audio path that cannot be played
- **THEN** queue-player marks the entry failed with enough detail for API/admin visibility

### Requirement: Track-sensitive playback

Manual queue playback SHALL avoid interrupting the currently playing track unless
an explicit admin skip command is used.

#### Scenario: Admin appends track

- **WHEN** an admin appends a track to the manual queue
- **THEN** Liquidsoap plays it at the next track-sensitive transition

#### Scenario: Admin skips current track

- **WHEN** an admin uses the skip control
- **THEN** the API sends the configured Liquidsoap telnet command and records the observable queue result
