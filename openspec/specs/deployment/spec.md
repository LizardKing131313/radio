## Purpose

Defines the production deployment shape. The target runtime is Kubernetes with a single kustomize root, explicit
workloads, and optional Ansible provisioning for a single VPS.
## Requirements
### Requirement: Kubernetes production root

The project SHALL deploy the production workload through `kubectl apply -k deploy`. The rendered manifests MUST be
validated before rollout, and a successful rollout MUST be followed by API, web, and HLS smoke checks.

#### Scenario: Fresh production apply

- **WHEN** required secrets and images are available
- **THEN** `kubectl apply -k deploy` creates or updates the namespace, database, migration job, app pod, services,
  ingress, and backup job
- **AND** `kubectl kustomize deploy` succeeds before apply

#### Scenario: Production rollout is ready

- **WHEN** the radio deployment reports all required containers ready
- **THEN** `/api/health`, `/player`, `/admin`, and the HLS master playlist return successful responses

### Requirement: Kubernetes owns process lifecycle

Long-running radio processes MUST be modeled as Kubernetes-managed containers or jobs, not as a Python supervisor inside
the application.

#### Scenario: Worker process exits

- **WHEN** search, prefetch, queue-player, API, Liquidsoap, FFmpeg, or Nginx exits unexpectedly
- **THEN** kubelet restarts the owning container according to the workload policy

#### Scenario: Python command wraps FFmpeg

- **WHEN** `python -m manager ffmpeg-hls` starts
- **THEN** Python assembles arguments and execs `ffmpeg`
- **AND** it does not supervise FFmpeg with a custom process manager

### Requirement: Optional VPS provisioning

The project SHALL keep single-VPS provisioning in Ansible without making Ansible the application runtime orchestrator.

#### Scenario: VPS bootstrap

- **WHEN** Ansible provisioning runs against the target host
- **THEN** it installs the required host packages, builds or deploys the image, and applies Kubernetes manifests

### Requirement: Reliable Ansible SSH transport

Production Ansible deployments SHALL use a non-multiplexed SSH transport that does not depend on a WSL control socket.
When Ansible runs from WSL on Windows, it SHALL be able to use the Windows OpenSSH executable with
`ControlMaster=no` and `ControlPath=none`.

#### Scenario: Deploy from WSL controller

- **WHEN** an operator runs an origin or edge deployment from WSL
- **THEN** Ansible connects through the configured working SSH executable
- **AND** the playbook does not fail because of a local WSL-vsock/control-socket error

### Requirement: Edge proxy DNS path

The public edge hostname SHALL resolve directly to the edge VPS without a Cloudflare proxy layer when serving the live
HLS stream. TLS SHALL terminate at the edge nginx using its managed Let's Encrypt certificate.

#### Scenario: Edge HLS request

- **WHEN** a client requests the edge hostname
- **THEN** DNS routes it directly to the edge VPS
- **AND** nginx proxies the request to the origin over IPv4 with the origin Host and TLS SNI

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

### Requirement: Scheduled retention workload

The Kubernetes deployment SHALL include a dedicated CronJob for retention that uses the production application image,
the PostgreSQL Secret, the radio config ConfigMap, and the existing cache PVC.

#### Scenario: Retention CronJob is rendered

- **WHEN** `kubectl kustomize deploy` renders the manifests
- **THEN** a retention CronJob is present with `concurrencyPolicy: Forbid`
- **AND** its command runs `python -m manager retention --delete`
- **AND** it mounts the cache PVC and can reach PostgreSQL
