## Purpose

Defines the HTTP behavior exposed by the radio manager API. The API is a thin FastAPI layer over repositories and
runtime files; it does not own process lifecycle or orchestration.

## Requirements

### Requirement: Health and telemetry endpoints

The API SHALL expose health and metrics endpoints that report runtime state without mutating playback, queue, or search
state.

#### Scenario: Health check includes external API state

- **WHEN** a client requests `/api/health`
- **THEN** the response includes service health and YouTube API quota/error state
- **AND** the request does not trigger search, download, or playback work

#### Scenario: Metrics endpoint is read-only

- **WHEN** a client requests `/api/metrics` or `/api/metrics/prometheus`
- **THEN** the API returns current runtime counters
- **AND** no queue entry or track row is changed

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

### Requirement: Admin mutations

The API SHALL require the configured admin bearer token for queue and offer mutations that change playback or moderation
state.

#### Scenario: Missing admin token

- **WHEN** a mutation request omits `Authorization: Bearer <token>`
- **THEN** the API rejects the request before changing database or playback state

#### Scenario: Valid admin token

- **WHEN** a mutation request includes the configured admin token
- **THEN** the API applies the requested queue or offer change through the domain layer

### Requirement: Web client shell endpoints

The HTTP surface SHALL expose web-client shell and static asset responses without changing existing JSON API semantics.

#### Scenario: Player shell is requested

- **WHEN** a client requests the public player route
- **THEN** the response is an HTML shell for the player web client
- **AND** the response does not perform playback, queue, search, download, or database mutation work

#### Scenario: Admin shell is requested

- **WHEN** a client requests the admin web-client route
- **THEN** the response is an HTML shell for the admin web client
- **AND** the response does not include the configured admin token
- **AND** admin mutations still require bearer authorization through the existing API endpoints

#### Scenario: Static asset is requested

- **WHEN** a client requests a built web-client static asset
- **THEN** the response serves that asset with an appropriate content type
- **AND** hashed immutable assets can be cached separately from shell documents

### Requirement: API namespace remains stable

The system SHALL keep existing JSON API endpoints under the `/api/` edge namespace while adding browser-facing
web-client routes.

#### Scenario: Existing API endpoint is requested

- **WHEN** a client requests an existing endpoint such as `/api/current`, `/api/metrics`, `/api/tracks`, or
  `/api/offers`
- **THEN** the endpoint returns the existing JSON contract
- **AND** the request is not routed to a web-client shell

#### Scenario: Unknown web route is requested

- **WHEN** a browser requests an unknown route intended for client-side navigation
- **THEN** the system returns the appropriate web-client shell or a clear not-found response
- **AND** `/api/` and `/hls/` paths are not swallowed by client-side fallback routing
