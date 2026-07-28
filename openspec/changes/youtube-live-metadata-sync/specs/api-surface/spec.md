## MODIFIED Requirements

### Requirement: Current playback endpoint

The API SHALL expose the currently audible track estimate using Liquidsoap nowplaying data and the configured HLS live
offset, and SHALL include the configured YouTube Live metadata state.

#### Scenario: Current track is available

- **WHEN** Liquidsoap has written current metadata
- **THEN** `/api/current` returns the track metadata and offset-adjusted timing
- **AND** returns the YouTube Live metadata state

#### Scenario: Current track is unknown

- **WHEN** runtime metadata is missing or stale
- **THEN** `/api/current` returns a valid response that makes the unknown state explicit
- **AND** still returns the YouTube Live metadata state
