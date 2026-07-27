## MODIFIED Requirements

### Requirement: Missing audio processing

Система SHALL process active tracks without audio path from PostgreSQL and write download results back to the track
repository. The production download path MUST have the JavaScript runtime required by its explicit `yt-dlp` invocation.

#### Scenario: Cold file already exists

- **WHEN** track has no audio path but cold cache file exists
- **THEN** prefetch treats it as cache hit
- **AND** updates track audio path to the cold file
- **AND** ensures a hot copy exists

#### Scenario: Download succeeds

- **WHEN** yt-dlp downloads an opus file successfully with its configured JavaScript runtime
- **THEN** prefetch measures LUFS when possible
- **AND** stores audio path, cold cache state, last prefetch time, and reset fail count

#### Scenario: Download fails

- **WHEN** yt-dlp exits unsuccessfully or processing raises an error
- **THEN** prefetch increments track fail count
- **AND** records a temporary blacklist backoff for the YouTube id

### Requirement: yt-dlp isolation

Система MUST invoke `yt-dlp` only in the prefetch path, not in search.

#### Scenario: Audio download is needed

- **WHEN** prefetch downloads a track
- **THEN** command uses `yt-dlp`, extracts opus audio, avoids playlists, uses configured timeout, and requests the
  `node` JavaScript runtime

#### Scenario: Search discovers metadata

- **WHEN** search worker discovers tracks
- **THEN** it stores metadata only and does not download audio
