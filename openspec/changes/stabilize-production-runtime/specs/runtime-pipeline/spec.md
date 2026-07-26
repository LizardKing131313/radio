## MODIFIED Requirements

### Requirement: Continuous audio output

The runtime SHALL feed Liquidsoap output through the shared FIFO into FFmpeg, which SHALL write advancing HLS files
served by Nginx. A restart of FFmpeg MUST not require a database migration or a change to the Liquidsoap source graph.

#### Scenario: Cached tracks exist

- **WHEN** the cache contains playable tracks
- **THEN** Liquidsoap selects audio, FFmpeg writes HLS output, and Nginx serves the playlist and segments

#### Scenario: FFmpeg restarts

- **WHEN** the FFmpeg container restarts while Liquidsoap continues running
- **THEN** FFmpeg recreates its HLS directories and resumes reading the shared FIFO
- **AND** a new HLS playlist and segments become available without database changes
