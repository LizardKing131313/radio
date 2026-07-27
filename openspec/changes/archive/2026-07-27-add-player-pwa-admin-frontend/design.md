## Context

The radio backend already exposes the domain surface needed by a player and admin UI: `/api/current`, `/api/metrics`,
`/api/tracks`, `/api/offers`, queue mutations, and HLS files under `/hls/`. The current admin page is a large inline
`ADMIN_HTML` string in `manager/api/app.py`, which makes browser UI hard to maintain and couples frontend growth to the
API module.

Kubernetes owns runtime lifecycle. This change must not add a Node server, SSR process, Redis, queues, or a new
database. The UI can be a static client built at image-build time and served by the existing HTTP path.

## Goals / Non-Goals

**Goals:**

- Provide a maintainable public player web app that can be installed as a PWA.
- Replace inline admin HTML with a separate admin web client that reuses existing API mutations.
- Keep frontend source isolated from Python backend modules while sharing a typed API client between player and admin
  code.
- Serve built frontend assets through the existing FastAPI/Nginx/Kubernetes deployment shape.
- Leave room for later Capacitor/native wrappers without committing this change to mobile, car, or TV store packaging.

**Non-Goals:**

- No native iOS/Android app, Android Auto, CarPlay, Android TV, tvOS, Tizen, or webOS store package in this change.
- No replacement of the FastAPI backend, PostgreSQL repositories, Liquidsoap, FFmpeg, or HLS pipeline.
- No server-side rendering or authenticated multi-user admin system.
- No broad redesign of search, queue playback, or offers workflows beyond what the admin UI needs to call.

## Decisions

### Use a static TypeScript frontend workspace

Create a `frontend/` workspace with separate app entry points for the player and admin, plus small shared packages for
API calls and UI primitives only when both apps use them. Use Vite as the build tool, Tailwind CSS v4 for styling, and a
small component runtime such as Preact/React.

Alternatives considered:

- Python templates plus HTMX: good for internal admin, but not enough for a polished PWA audio player, service worker,
  media session handling, and future mobile wrappers.
- Django Admin: strong CRUD admin, but would duplicate the existing FastAPI/SQLAlchemy stack and is not intended as a
  public frontend.
- Reflex/NiceGUI/Streamlit-style Python UI: fast for dashboards, but poor fit for browser media APIs, PWA
  installability, and static cross-platform delivery.
- Native-first Expo/React Native: useful if app-store mobile is the immediate goal, but heavier than the current
  requirement and weaker for browser-first PWA delivery.

### Serve built assets from FastAPI behind existing Nginx

Build frontend assets into the application image and let FastAPI serve static files and shell documents with
`Cache-Control` appropriate to each file type. Nginx keeps direct `/hls/` serving and proxies `/api/` plus web-client
routes to the API container.

This avoids a separate UI container or runtime Node process. It also allows local tests to verify route behavior with
the existing FastAPI test style.

### Keep HLS playback web-native

The player uses an HTML media element. It should prefer native HLS support when the browser can play the selected
playlist, and use `hls.js` only where Media Source Extensions are needed. The UI should expose one clear user-initiated
play action because mobile browsers commonly block autoplay until interaction.

The player should select from the existing TS/fMP4 HLS outputs and surface failures clearly instead of hiding playback
errors.

### Make PWA offline behavior conservative

The service worker caches the app shell and static hashed assets only. It must not cache live HLS segments, playlist
responses, admin mutation responses, or bearer tokens. `/api/current` and HLS playlist requests stay network-first
because stale playback state is worse than an explicit offline state.

### Keep admin auth on existing bearer-token model

The admin client sends `Authorization: Bearer <token>` to existing mutation endpoints. The server continues to reject
missing/invalid tokens before mutation. This change does not introduce users, sessions, OAuth, RBAC, or password
recovery.

### Use tests to enforce boundaries

Python tests should cover static shell routing, headers, and continued API behavior. Frontend tests should cover API
client URL construction, player state transitions, and admin action calls. A lightweight repository check should prevent
reintroducing large inline HTML/JS strings into backend modules.

## Risks / Trade-offs

- Tailwind CSS v4 targets modern browsers and may not work on older smart TV web engines -> Treat TV web support as
  future validation; if old TV support becomes a hard requirement, add a compatibility decision or switch generated CSS
  strategy in a separate change.
- `hls.js` adds frontend bundle weight -> Load it only when native playback is unavailable.
- Service workers can hold stale assets -> Use hashed asset filenames and a simple update flow that activates new caches
  predictably.
- Admin bearer tokens in a browser are sensitive -> Never bake tokens into assets, keep transport HTTPS-only in
  production, and keep admin routes no-store where practical.
- A frontend toolchain adds Node build complexity -> Keep it build-time only and avoid a runtime Node container.
- Future native car/TV support will still require platform-specific wrappers -> Reuse the API/HLS contract, but do not
  pretend PWA alone satisfies CarPlay, Android Auto, or TV store requirements.

## Migration Plan

1. Add the frontend workspace, package metadata, build scripts, and generated static output location.
2. Implement player/admin static shell routes and static file serving in FastAPI while keeping JSON APIs under `/api/`.
3. Update Nginx config to proxy web shell/static routes to API and keep `/hls/` served directly from `/opt/radio/www`.
4. Replace the inline admin route with the new admin shell route; keep existing admin mutation endpoints unchanged.
5. Update the Docker image build to compile frontend assets and copy only build output into the runtime image.
6. Validate locally with OpenSpec, Python tests, frontend checks, and `make ci`.

Rollback is straightforward: revert the frontend build/static route changes and restore the previous inline admin route
if needed. No database migration is involved.

## Open Questions

- Final visual branding, icon artwork, and app name for the installable PWA.
- Exact minimum browser/TV engine support matrix after real-device testing.
- Whether the admin token should support an explicit "remember on this device" option or session-only storage.
