# Online Radio

[![CI](https://github.com/LizardKing131313/radio/actions/workflows/ci.yml/badge.svg)](https://github.com/LizardKing131313/radio/actions/workflows/ci.yml)
[![CI-Meta](https://github.com/LizardKing131313/radio/actions/workflows/ci-meta.yml/badge.svg)](https://github.com/LizardKing131313/radio/actions/workflows/ci-meta.yml)
[![Qodana](https://github.com/LizardKing131313/radio/actions/workflows/qodana_code_quality.yml/badge.svg)](https://github.com/LizardKing131313/radio/actions/workflows/qodana_code_quality.yml)
![Coverage](badges/coverage.svg)

## Development

Non-trivial behavior, API, persistence, runtime and deployment changes go through
OpenSpec first, then tests, then implementation. Local gate:

```bash
make ci
```

Workflow details: [docs/development-process.md](docs/development-process.md).

## Deployment

The production target is Kubernetes:

```bash
cp deploy/k8s/secret.example.yaml deploy/k8s/secret.yaml
# edit deploy/k8s/secret.yaml locally; it is ignored by git
docker build -t radio-manager:latest -f docker/app/Dockerfile .
kubectl apply -k deploy
kubectl -n radio wait --for=condition=complete job/alembic --timeout=180s
```

PostgreSQL schema is managed by Alembic from `alembic/versions`.
Search uses YouTube Data API; downloads still use `yt-dlp`.
FastAPI is exposed under `/api/`; `/current` includes Liquidsoap nowplaying plus HLS offset, `/health` includes YouTube
API telemetry, `/metrics` returns compact runtime JSON, `/metrics/prometheus` returns Prometheus exposition, and admin
mutations require `RADIO_ADMIN_TOKEN`.
The public player is served at `/player` as an installable PWA, and the admin shell is served at `/admin`.
Kubernetes owns runtime process restarts: search, prefetch, queue-player, API, Liquidsoap, FFmpeg and Nginx are separate
containers in the `radio` pod.
Manual admin queue uses Liquidsoap `request.queue`; downloads still use `yt-dlp`.

Frontend checks live under `frontend/`:

```bash
cd frontend
npm install
npm run check
```

Runtime details: [docs/runtime.md](docs/runtime.md).

Single VPS provisioning is handled by Ansible: [ansible/README.md](ansible/README.md).
It installs Docker + k3s, creates the `radio` user, builds the image on the VPS and applies `deploy/`.
