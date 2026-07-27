## ADDED Requirements

### Requirement: Public player web client

The system SHALL provide a public browser-based player that can play the radio stream from the existing HLS output and
display current playback state from the API.

#### Scenario: Listener opens the player

- **WHEN** a listener opens the player route in a supported browser
- **THEN** the page renders a player shell with a clear play control
- **AND** the page requests current playback metadata from the API
- **AND** no admin token is required

#### Scenario: Listener starts playback

- **WHEN** the listener activates the play control
- **THEN** the player starts the compatible HLS stream
- **AND** playback errors are surfaced in the UI instead of failing silently

#### Scenario: Current metadata is unavailable

- **WHEN** the current playback API returns unknown or stale state
- **THEN** the player remains usable
- **AND** the UI makes the unknown state explicit

### Requirement: Installable PWA behavior

The public player SHALL expose installable PWA metadata and offline app-shell behavior without caching live stream
content.

#### Scenario: Browser checks installability

- **WHEN** a PWA-capable browser loads the player over HTTPS
- **THEN** the response includes a web app manifest with app name, start URL, display mode, theme colors, and icons
- **AND** the page registers a service worker for the player scope

#### Scenario: Listener reopens without network

- **WHEN** a listener reopens the installed player while network access is unavailable
- **THEN** the cached app shell loads
- **AND** the UI reports that live playback and current metadata require connectivity

#### Scenario: Live HLS content is requested

- **WHEN** the player or service worker handles HLS playlist or segment requests
- **THEN** live playlist and segment responses are not stored in a long-lived offline cache

### Requirement: Browser media integration

The player SHALL integrate with browser media controls when the platform supports them while preserving a functional
in-page control path.

#### Scenario: Media Session API is available

- **WHEN** the browser exposes media session controls
- **THEN** the player publishes current title/artwork metadata when available
- **AND** supported play and pause actions control the same media element as the page controls

#### Scenario: Media Session API is unavailable

- **WHEN** the browser does not expose media session controls
- **THEN** the in-page player controls remain functional

### Requirement: Responsive and input-flexible UI

The player SHALL remain usable across phone, tablet, desktop, and large-screen browser layouts.

#### Scenario: Small viewport loads the player

- **WHEN** the player is opened on a narrow viewport
- **THEN** primary playback controls and current metadata are visible without horizontal scrolling

#### Scenario: Keyboard user operates the player

- **WHEN** a user navigates the player with a keyboard
- **THEN** interactive controls expose visible focus states
- **AND** the main play/pause action can be triggered without a pointer device

### Requirement: Admin web client

The system SHALL provide a separate admin web client that uses existing admin API mutations and does not embed server
secrets into frontend assets.

#### Scenario: Admin opens the admin route

- **WHEN** an operator opens the admin route
- **THEN** the admin shell renders track, queue, current playback, and telemetry areas using existing API data
- **AND** the shell does not include the configured admin token in HTML or static assets

#### Scenario: Admin mutation without token

- **WHEN** an operator attempts a queue, track, or offer mutation without an admin token
- **THEN** the UI prevents or reports the missing-token failure
- **AND** the API mutation is not treated as successful

#### Scenario: Admin mutation with token

- **WHEN** an operator performs a queue, track, or offer mutation with a valid admin token
- **THEN** the client sends the token as a bearer authorization header
- **AND** the UI refreshes affected state after the mutation succeeds

### Requirement: Client error states

The web clients SHALL expose clear loading, empty, offline, and error states for API and stream failures.

#### Scenario: API request fails

- **WHEN** a web client cannot load required API data
- **THEN** the affected area shows an actionable error state
- **AND** unrelated controls that can still function remain available

#### Scenario: Empty dataset is returned

- **WHEN** the API returns an empty queue, track list, or offers list
- **THEN** the client shows an explicit empty state instead of a broken table or blank page
