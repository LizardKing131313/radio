## Why

The current production image builds the frontend with Node.js but does not provide a JavaScript runtime in the final
image, so `yt-dlp` downloads fail or degrade in the running prefetch container. The running cluster also shows
intermittent FFmpeg FIFO errors, and the runtime/deployment contract does not yet require a successful end-to-end HLS
validation.

## What Changes

- Add an explicit production JavaScript runtime and `yt-dlp` runtime configuration for audio downloads.
- Define observable prefetch behavior when the JavaScript runtime is available and when a download still fails.
- Define FIFO-to-FFmpeg continuity checks for normal track transitions and process restart behavior.
- Add deployment validation requirements for rendered Kubernetes manifests and live API/player/HLS surfaces.
- Add focused tests before implementation and complete the existing frontend formatting/CI gate.

## Capabilities

### New Capabilities

- `production-runtime-validation`: Runtime prerequisites and end-to-end deployment checks for the radio pipeline.

### Modified Capabilities

- `prefetch-cache`: Require the configured JavaScript runtime for the `yt-dlp` download path and preserve existing
  failure/backoff behavior.
- `runtime-pipeline`: Require valid continuous audio delivery through the FIFO and HLS output.
- `deployment`: Require production-image runtime parity and live surface validation after deployment.
- `code-quality`: Require tests and minimal configuration for the new runtime behavior.

## Impact

- Affected code: Docker production image, prefetch command construction, FFmpeg/HLS runtime checks, and focused tests.
- Affected deployment: Kubernetes image build/rollout validation and smoke-check documentation.
- No database schema, API shape, new service, or secret-file changes.
- Validation: OpenSpec strict validation, Python tests, frontend checks, image build, Kubernetes render, and live
  HTTP/HLS smoke tests.
