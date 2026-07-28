## ADDED Requirements

### Requirement: Configured live metadata refresh

The system SHALL poll YouTube metadata for one configured video ID at the configured refresh interval and write the
normalized result to ephemeral runtime state.

#### Scenario: Live metadata succeeds

- **WHEN** the configured video ID returns valid YouTube metadata
- **THEN** runtime state records title, channel, broadcast status, timing fields, and update timestamps
- **AND** the search/catalog loop continues without interruption

#### Scenario: Live metadata is disabled

- **WHEN** no live video ID is configured
- **THEN** no YouTube live request is made
- **AND** runtime state reports an explicit disabled status

### Requirement: Refresh fallback

The system MUST preserve the last successful live metadata while recording a current error or stale status when a
refresh fails, and MUST not make the API or search worker fail because of that error.

#### Scenario: YouTube request fails

- **WHEN** the live metadata request returns an API, network, or malformed-response error
- **THEN** the worker records the error and last successful timestamp
- **AND** the API remains available

### Requirement: Current API exposure

The existing runtime response SHALL expose the live metadata state without changing queue or HLS behavior.

#### Scenario: Client requests current state

- **WHEN** a client requests `/current`
- **THEN** the response includes the live metadata state with disabled, unknown, stale, or successful status
- **AND** existing `now_playing` and `queue` fields remain available
