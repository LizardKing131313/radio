## Why

The current admin UI is embedded as a large HTML/CSS/JS string inside the FastAPI route module, which mixes API behavior
with browser UI and will not scale to a proper public player. The project needs a maintainable web-client surface that
can serve a public installable player and a separate admin UI while keeping FastAPI thin and Kubernetes-owned runtime
unchanged.

## What Changes

- Add a public player web client that plays the existing HLS output, displays current playback metadata from the API,
  and can be installed as a PWA.
- Add a separate admin web client that replaces the inline `ADMIN_HTML` implementation while reusing existing admin
  token API mutations.
- Add frontend project boundaries for app-specific code, shared API client code, shared UI primitives, static assets,
  PWA manifest, and service worker logic.
- Add production serving behavior for built frontend assets through the existing deployment shape without adding a new
  runtime service.
- Keep native mobile, CarPlay, Android Auto, and TV store packages out of this change; the web client should be
  structured so thin platform wrappers can reuse the same API/HLS surface later.

## Capabilities

### New Capabilities

- `web-client-surface`: Public player, installable PWA behavior, admin web client behavior, and browser-facing static
  asset behavior.

### Modified Capabilities

- `api-surface`: Define how FastAPI exposes web-client shell/static responses without moving domain behavior into UI
  routes.
- `deployment`: Define how built web-client assets are included and served in the existing Kubernetes/Nginx deployment
  shape.
- `code-quality`: Add frontend boundary and dependency discipline requirements so client code does not sprawl across
  backend modules.

## Impact

- Affected code: `manager/api/app.py`, deployment image/build files, Nginx/static serving config, and a new frontend
  workspace.
- Affected APIs: existing JSON and mutation endpoints are reused; small static/web shell routes may be added or changed.
- Dependencies: frontend tooling dependencies are expected for build-time client compilation; backend runtime
  dependencies should not grow unless required for static serving.
- Validation: `openspec validate --all --strict --no-interactive`, focused API/static route tests, frontend
  build/type/lint tests, and the existing `make ci` gate.
