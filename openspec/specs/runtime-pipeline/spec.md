## Purpose

Defines the end-to-end radio runtime pipeline from search through HLS delivery.
The system is built for continuous 24/7 playback with Kubernetes handling
process restarts.

## Requirements

### Requirement: Search to prefetch pipeline

The system SHALL discover candidate tracks through YouTube Data API and download
audio only through the prefetch path.

#### Scenario: Search discovers a track

- **WHEN** search receives a valid YouTube Data API result
- **THEN** it persists track metadata in PostgreSQL
- **AND** it does not invoke `yt-dlp`

#### Scenario: Prefetch finds an uncached track

- **WHEN** prefetch selects a track without an audio file
- **THEN** it downloads audio through `yt-dlp`, stores the file in cache, and updates PostgreSQL metadata

### Requirement: Continuous audio output

The runtime SHALL feed Liquidsoap output through FFmpeg into HLS files served by
Nginx.

#### Scenario: Cached tracks exist

- **WHEN** the cache contains playable tracks
- **THEN** Liquidsoap selects audio, FFmpeg writes HLS output, and Nginx serves the playlist and segments

#### Scenario: FFmpeg restarts

- **WHEN** the FFmpeg container restarts
- **THEN** it rebuilds HLS output from the runtime audio stream without requiring a database migration

### Requirement: Runtime telemetry

The runtime SHALL expose YouTube API quota/error state through a runtime JSON
file that the API can read.

#### Scenario: YouTube quota is exhausted

- **WHEN** YouTube Data API reports quota exhaustion
- **THEN** search writes that state to runtime info
- **AND** `/api/health` reports it without stopping already cached playback
