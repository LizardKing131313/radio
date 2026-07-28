## ADDED Requirements

### Requirement: YouTube Live configuration

The configuration SHALL support a non-secret YouTube Live video ID, refresh interval, and runtime state path, with an
empty video ID disabling the feature.

#### Scenario: Live configuration is omitted

- **WHEN** no `youtube_live` configuration is provided
- **THEN** defaults disable live polling
- **AND** application startup remains valid

#### Scenario: Live configuration is set

- **WHEN** a valid video ID and positive refresh interval are configured
- **THEN** the worker uses those values for metadata refresh
- **AND** no stream key or RTMP secret is required
