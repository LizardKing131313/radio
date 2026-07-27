## ADDED Requirements

### Requirement: Production runtime prerequisites

The production image SHALL contain every executable explicitly required by the running prefetch and media pipeline,
including a JavaScript runtime addressable as `node` by `yt-dlp`.

#### Scenario: Production image is inspected

- **WHEN** the built production image runs `node --version` and `yt-dlp --version`
- **THEN** both commands exit successfully
- **AND** the image can execute the existing `yt-dlp --js-runtimes node` download path

### Requirement: Deployment smoke validation

The deployment validation SHALL verify rendered Kubernetes manifests and the observable API, web, and HLS surfaces after
rollout.

#### Scenario: Running namespace is checked

- **WHEN** the radio deployment is ready
- **THEN** `/api/health`, `/api/current`, `/player`, `/admin`, and the HLS master playlist return successful responses
- **AND** the radio pod reports all required containers ready

### Requirement: HLS continuity validation

The deployment validation SHALL verify that HLS playlists remain readable and new segments continue to appear while the
radio is running.

#### Scenario: HLS output is active

- **WHEN** the HLS master playlist and a variant playlist are fetched twice with a segment interval between requests
- **THEN** both responses remain valid
- **AND** the variant playlist advances or references available current segments
