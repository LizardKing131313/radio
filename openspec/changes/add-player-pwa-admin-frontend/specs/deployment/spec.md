## ADDED Requirements

### Requirement: Web client assets in production deployment

The production deployment SHALL include the built web-client assets needed to serve the player and admin UI through the
existing `radio` HTTP service.

#### Scenario: Fresh production apply with web assets

- **WHEN** the production image and manifests are applied with `kubectl apply -k deploy`
- **THEN** the resulting HTTP service can serve the player shell, admin shell, manifest, service worker, and static
  assets
- **AND** no separate long-running Node or frontend server container is required

#### Scenario: API container starts

- **WHEN** the API container starts from the production image
- **THEN** the built web-client assets required by the configured web routes are present
- **AND** missing assets fail readiness or tests before production rollout rather than returning a broken shell

### Requirement: Nginx routing for web clients, API, and HLS

The production Nginx configuration SHALL keep direct HLS serving and API proxying distinct from web-client shell
routing.

#### Scenario: HLS request is received

- **WHEN** Nginx receives a request under `/hls/`
- **THEN** it serves the request from the HLS output volume as before
- **AND** web-client fallback routing does not intercept the request

#### Scenario: API request is received

- **WHEN** Nginx receives a request under `/api/`
- **THEN** it proxies the request to the FastAPI container as before
- **AND** web-client fallback routing does not intercept the request

#### Scenario: Web client request is received

- **WHEN** Nginx receives a request for a player, admin, manifest, service worker, or static asset route
- **THEN** it routes the request to the component that serves built web-client files
- **AND** the request does not require an additional Kubernetes Service
