## Context

The radio already separates frontend build and Python runtime stages, uses
`yt-dlp --js-runtimes node` in the prefetch command, and lets Kubernetes own the lifecycle of search, prefetch,
Liquidsoap, FFmpeg, API, and Nginx. The running prefetch container nevertheless reports that no supported JavaScript
runtime is available because Node.js exists only in the frontend build stage. The running cluster also needs an explicit
end-to-end check for FIFO input, HLS output, and public HTTP surfaces.

## Goals / Non-Goals

**Goals:**

- Make the existing `yt-dlp` Node runtime requirement true in the final image.
- Preserve the existing prefetch blacklist/backoff behavior when downloads fail.
- Verify continuous FIFO-to-FFmpeg-to-HLS output and recovery after an FFmpeg restart.
- Make deployment validation observable and repeatable.

**Non-Goals:**

- No new service, queue, database table, API endpoint, or secret mechanism.
- No replacement of Liquidsoap, FFmpeg, Kubernetes, or the existing cache model.
- No change to YouTube search, queue semantics, or frontend behavior beyond formatting.

## Decisions

- Install the smallest available Node.js runtime in the final Debian image and keep the existing explicit
  `--js-runtimes node` argument. This reuses the current downloader contract instead of adding configuration or a
  wrapper.
- Add focused tests around the existing command builder and FFmpeg argument builder. Use deployment smoke commands for
  process/file continuity rather than mocking an entire Kubernetes cluster in Python.
- Treat a non-zero downloader exit as the existing recoverable failure path:
  log it, increment failure state, and apply blacklist backoff. The runtime prerequisite is fixed without changing retry
  policy.
- Validate manifests with `kubectl kustomize`, then validate a running namespace through `/api/health`, `/api/current`,
  `/player`, `/admin`, and the HLS master playlist. Kubernetes remains responsible for restarts.

## Risks / Trade-offs

- [Risk] Debian's Node.js package version can differ from the frontend build image. -> [Mitigation] The contract
  requires only the supported `node`
  executable and a production-image smoke check; frontend build remains pinned by its lockfile.
- [Risk] A FIFO/FFmpeg error may be caused by a runtime race rather than bad command arguments. -> [Mitigation] Test
  restart and segment freshness in the deployed pod before changing application behavior.
- [Risk] External YouTube blocking or age restrictions can still fail specific videos. -> [Mitigation] Keep per-track
  failure/backoff behavior and use a known playable fixture for runtime smoke validation.

## Migration Plan

1. Update specs and tests.
2. Add Node.js to the final image and build a new image.
3. Render manifests and run the focused local checks.
4. Roll out the image with Kubernetes and verify API/player/HLS surfaces.
5. Roll back to the previous image if HLS continuity or prefetch health regresses; no schema migration is involved.
