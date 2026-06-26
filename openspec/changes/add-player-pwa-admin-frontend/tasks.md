## 1. Test Coverage First

- [x] 1.1 Add failing or updated Python tests for player shell, admin shell, static asset headers, manifest, service
  worker, and unchanged `/api/` JSON routing.
- [x] 1.2 Add a boundary test or repository check that fails when large inline browser UI blocks are reintroduced into
  backend API modules.
- [x] 1.3 Add frontend test scaffolding for API client URL/header behavior, player playback state transitions, and admin
  mutation calls.

## 2. Frontend Workspace Setup

- [x] 2.1 Add a `frontend/` workspace with player and admin app entry points plus minimal shared package boundaries.
- [x] 2.2 Add Vite, TypeScript, Tailwind CSS v4, and the smallest required runtime dependencies for static browser
  clients.
- [x] 2.3 Configure build output so generated static assets can be copied into the Python application image without
  committing build artifacts.
- [x] 2.4 Add frontend scripts for build, lint/typecheck, and tests.

## 3. Shared Client and Player PWA

- [x] 3.1 Implement the shared API client for current playback, metrics, tracks, offers, and authorized mutations using
  existing endpoint contracts.
- [x] 3.2 Implement the public player shell with responsive layout, loading/empty/error/offline states, and current
  metadata display.
- [x] 3.3 Implement HLS playback with native support first and lazy `hls.js` fallback only when required.
- [x] 3.4 Add browser media integration through feature-detected Media Session API handlers.
- [x] 3.5 Add PWA manifest, icons/placeholders, service worker registration, and conservative app-shell caching that
  excludes `/api/` and `/hls/`.

## 4. Admin Web Client

- [x] 4.1 Implement the admin shell using existing metrics/current/tracks/offers data without embedding the admin token.
- [x] 4.2 Implement token entry/storage behavior and bearer authorization headers for existing admin mutations.
- [x] 4.3 Implement queue, track, and offer actions with refresh-after-success and clear failure states.
- [x] 4.4 Preserve mobile-friendly table/card behavior and keyboard-visible focus states.

## 5. Backend and Deployment Integration

- [x] 5.1 Replace the inline `ADMIN_HTML` route with static web-client shell serving while keeping FastAPI route bodies
  thin.
- [x] 5.2 Mount built static assets and set cache headers so shell documents are revalidated and hashed assets are
  cacheable.
- [x] 5.3 Update Nginx routing so `/hls/` remains direct, `/api/` remains proxied, and web-client routes reach the
  static shell/assets.
- [x] 5.4 Update Docker build steps to compile frontend assets and copy only production build output into the runtime
  image.
- [x] 5.5 Update runtime/development docs with player/admin URLs, frontend commands, and deployment notes.

## 6. Validation

- [x] 6.1 Run `openspec validate --all --strict --no-interactive`.
- [x] 6.2 Run frontend build, lint/typecheck, and test commands.
- [x] 6.3 Run focused Python tests for API/static routing.
- [ ] 6.4 Run `make ci`.
