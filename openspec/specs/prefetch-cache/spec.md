## Purpose

Фиксирует поведение prefetch worker и audio cache. Prefetch отвечает за
скачивание audio через yt-dlp, cold/hot cache maintenance, blacklist backoff и
обновление track cache metadata в PostgreSQL.

## Requirements

### Requirement: Missing audio processing

Система SHALL process active tracks without audio path from PostgreSQL and write
download results back to the track repository.

#### Scenario: Cold file already exists

- **WHEN** track has no audio path but cold cache file exists
- **THEN** prefetch treats it as cache hit
- **AND** updates track audio path to the cold file
- **AND** ensures a hot copy exists

#### Scenario: Download succeeds

- **WHEN** yt-dlp downloads an opus file successfully
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
- **THEN** command uses `yt-dlp`, extracts opus audio, avoids playlists, and uses configured timeout

#### Scenario: Search discovers metadata

- **WHEN** search worker discovers tracks
- **THEN** it stores metadata only and does not download audio

### Requirement: Cache hygiene

Система SHALL keep cache directories safe for Liquidsoap playlist reads.

#### Scenario: Non-audio files are present

- **WHEN** cold or hot cache contains files without an allowed audio suffix
- **THEN** prefetch removes those files during the tick

#### Scenario: Hot copy is created

- **WHEN** a cold audio file is promoted to hot cache
- **THEN** prefetch copies through a temp file and atomically replaces the final hot file

### Requirement: Cache limits

Система MUST enforce cold cache byte quota and hot cache item count.

#### Scenario: Cold cache exceeds quota

- **WHEN** cold cache total size is greater than configured quota
- **THEN** oldest files are removed until usage is within quota

#### Scenario: Hot cache overflows

- **WHEN** hot cache has more files than `hot_max_items`
- **THEN** oldest hot files are removed

### Requirement: Blacklist backoff

Система SHALL store temporary per-YouTube-id download backoff in JSON and reset
it after a successful cache hit or download.

#### Scenario: Failed item is still in backoff

- **WHEN** blacklist `until_ts` is in the future for a YouTube id
- **THEN** prefetch skips that item for the current tick

#### Scenario: Item later succeeds

- **WHEN** prefetch successfully finds or downloads the audio file
- **THEN** the YouTube id is removed from blacklist state
