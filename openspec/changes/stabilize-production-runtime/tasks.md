## 1. Tests First

- [x] 1.1 Add or update a prefetch command test proving the existing downloader requests `--js-runtimes node` and
  preserves timeout, opus, and no-playlist options.
- [x] 1.2 Add or update FFmpeg tests proving runtime directories are recreated and the existing FIFO/HLS argument
  contract remains intact.
- [x] 1.3 Add a deployment validation script or focused command coverage for rendered manifests and the required API,
  web, and HLS smoke endpoints without embedding secrets.

## 2. Production Runtime

- [x] 2.1 Extend the final stage of `docker/app/Dockerfile` with the smallest Node.js runtime needed by the existing
  `yt-dlp --js-runtimes node` invocation.
- [x] 2.2 Build the production image and verify `node --version`, `yt-dlp --version`, and the downloader runtime path
  inside the image.
- [x] 2.3 Reuse the existing prefetch process and blacklist/backoff path; do not add a new downloader abstraction or
  configuration layer.

## 3. FIFO And HLS Runtime

- [x] 3.1 Reproduce the observed FFmpeg FIFO errors in the local/container runtime and identify whether they come from
  restart ordering, input format, or argument construction.
- [x] 3.2 Implement the smallest fix required by the failing test and preserve Kubernetes ownership of FFmpeg lifecycle.
- [x] 3.3 Verify playlist and segment advancement across normal track transitions and an FFmpeg restart.

## 4. Frontend And Validation

- [x] 4.1 Apply the repository Prettier configuration to the 17 reported frontend files without changing UI behavior.
- [x] 4.2 Run `openspec validate --all --strict --no-interactive`.
- [x] 4.3 Run `make ci` and resolve any failures.
- [x] 4.4 Run `kubectl kustomize deploy` and the live namespace smoke checks when a cluster is available.
- [x] 4.5 Mark completed tasks and record remaining external VPS/TLS checks in the change notes.

## Validation Notes

- OpenSpec strict validation: 17/17 passed.
- `make ci`: passed; Python 104 passed and 1 skipped, frontend checks/build passed.
- `kubectl kustomize deploy`: passed; basic Kubernetes web/API/HLS smoke passed.
- Existing cluster HLS advancement check failed on the pre-change deployment: the playlist stayed on the same media
  sequence after 12 seconds while Liquidsoap continued updating now-playing metadata.
- Production Docker build succeeded after reusing the existing frontend Node binary in the final image; the image passed
  `node --version` and `yt-dlp --version` checks.
- The local Docker Desktop rollout used the new image, found Node in the running prefetch container, and passed HLS
  advancement after an isolated FFmpeg container restart.
- External VPS, DNS, and TLS rollout checks remain pending until the real target deployment is selected.
