## ADDED Requirements

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
