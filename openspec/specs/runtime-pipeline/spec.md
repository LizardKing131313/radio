## Purpose

Defines the end-to-end radio runtime pipeline from search through HLS delivery. The system is built for continuous 24/7
playback with Kubernetes handling process restarts.

## Requirements

### Requirement: Search to prefetch pipeline

The system SHALL discover candidate tracks through YouTube Data API and download audio only through the prefetch path.

#### Scenario: Search discovers a track

- **WHEN** search receives a valid YouTube Data API result
- **THEN** it persists track metadata in PostgreSQL
- **AND** it does not invoke `yt-dlp`

#### Scenario: Prefetch finds an uncached track

- **WHEN** prefetch selects a track without an audio file
- **THEN** it downloads audio through `yt-dlp`, stores the file in cache, and updates PostgreSQL metadata

### Requirement: Continuous audio output

The runtime SHALL feed Liquidsoap output through FFmpeg into HLS files served by Nginx.

#### Scenario: Cached tracks exist

- **WHEN** the cache contains playable tracks
- **THEN** Liquidsoap selects audio, FFmpeg writes HLS output, and Nginx serves the playlist and segments

#### Scenario: FFmpeg restarts

- **WHEN** the FFmpeg container restarts
- **THEN** it rebuilds HLS output from the runtime audio stream without requiring a database migration

### Requirement: Edge-compatible HLS playback

The public player SHALL use a stable live HLS rendition and recover from transient network or media errors instead of
remaining stuck in a playing state with no advancing audio time. The origin SHALL retain at least 12 two-second segments
so an edge proxy has a sufficient fetch window while the origin rotates files.

#### Scenario: Browser starts playback through edge

- **WHEN** the player loads the public edge URL
- **THEN** it uses the stable `v64k` fMP4 rendition
- **AND** playback starts six segments behind the live edge to tolerate proxy latency
- **AND** the audio time continues advancing after at least 30 seconds

#### Scenario: HLS segment or media error

- **WHEN** Hls.js reports a fatal network or media error
- **THEN** it retries loading or recovers the media pipeline
- **AND** it does not silently leave the audio element playing while stalled

### Requirement: Jingle rotation

The normal library rotation SHALL play two library tracks followed by one random jingle, repeating without a wall-clock
test timer or forced track skips.

#### Scenario: Library rotation reaches the jingle slot

- **WHEN** two library tracks have completed
- **THEN** Liquidsoap selects one jingle at random from the bundled jingle files
- **AND** playback continues with the library after the jingle finishes

#### Scenario: Normal track transition

- **WHEN** a library track or jingle reaches its transition boundary
- **THEN** the configured crossfade overlaps the outgoing and incoming audio
- **AND** Liquidsoap does not skip a track on a fixed short timer

### Requirement: Runtime telemetry

The runtime SHALL expose YouTube API quota/error state through a runtime JSON file that the API can read.

#### Scenario: YouTube quota is exhausted

- **WHEN** YouTube Data API reports quota exhaustion
- **THEN** search writes that state to runtime info
- **AND** `/api/health` reports it without stopping already cached playback
