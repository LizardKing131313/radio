## Purpose

Defines the HTTP behavior exposed by the radio manager API. The API is a thin
FastAPI layer over repositories and runtime files; it does not own process
lifecycle or orchestration.

## Requirements

### Requirement: Health and telemetry endpoints

The API SHALL expose health and metrics endpoints that report runtime state
without mutating playback, queue, or search state.

#### Scenario: Health check includes external API state

- **WHEN** a client requests `/api/health`
- **THEN** the response includes service health and YouTube API quota/error state
- **AND** the request does not trigger search, download, or playback work

#### Scenario: Metrics endpoint is read-only

- **WHEN** a client requests `/api/metrics` or `/api/metrics/prometheus`
- **THEN** the API returns current runtime counters
- **AND** no queue entry or track row is changed

### Requirement: Current playback endpoint

The API SHALL expose the currently audible track estimate using Liquidsoap
nowplaying data and the configured HLS live offset.

#### Scenario: Current track is available

- **WHEN** Liquidsoap has written current metadata
- **THEN** `/api/current` returns the track metadata and offset-adjusted timing

#### Scenario: Current track is unknown

- **WHEN** runtime metadata is missing or stale
- **THEN** `/api/current` returns a valid response that makes the unknown state explicit

### Requirement: Admin mutations

The API SHALL require the configured admin bearer token for queue and offer
mutations that change playback or moderation state.

#### Scenario: Missing admin token

- **WHEN** a mutation request omits `Authorization: Bearer <token>`
- **THEN** the API rejects the request before changing database or playback state

#### Scenario: Valid admin token

- **WHEN** a mutation request includes the configured admin token
- **THEN** the API applies the requested queue or offer change through the domain layer
