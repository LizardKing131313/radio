## MODIFIED Requirements

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
