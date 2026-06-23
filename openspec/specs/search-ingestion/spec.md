## Purpose

Фиксирует search worker и YouTube Data API ingestion. Search получает только
metadata, фильтрует кандидатов и сохраняет каталог через PostgreSQL repo.

## Requirements

### Requirement: YouTube metadata search

Система SHALL use YouTube Data API search and videos endpoints to build track
metadata windows.

#### Scenario: Search window is valid

- **WHEN** title, API key, start, and end are valid
- **THEN** search calls `search.list` for video snippets
- **AND** calls `videos.list` for duration and normalized metadata

#### Scenario: Search input is invalid

- **WHEN** title or API key is blank, start is below one, or end is before start
- **THEN** search returns an empty result without external API calls

### Requirement: Candidate filtering

Система MUST filter YouTube candidates before storing them in the catalog.

#### Scenario: Candidate is live or upcoming

- **WHEN** YouTube item reports live or upcoming broadcast content
- **THEN** search excludes the item

#### Scenario: Candidate duration is outside allowed range

- **WHEN** duration is below 60 seconds or above 600 seconds
- **THEN** search excludes the item

#### Scenario: Candidate title does not contain query

- **WHEN** normalized title does not contain the configured search title
- **THEN** search excludes the item

### Requirement: Track upsert

Система SHALL upsert accepted search results by YouTube id without clearing
existing downloaded audio metadata.

#### Scenario: New track is discovered

- **WHEN** accepted metadata has an unknown YouTube id
- **THEN** repository inserts a new active track with URL, title, duration, channel, and thumbnail

#### Scenario: Existing track is refreshed

- **WHEN** accepted metadata has a known YouTube id
- **THEN** repository refreshes metadata
- **AND** keeps existing audio path and loudness unless new non-null values are provided

### Requirement: YouTube API telemetry

Система MUST record YouTube API success and error state to runtime telemetry
JSON.

#### Scenario: Search window succeeds

- **WHEN** a search window returns successfully
- **THEN** telemetry records status ok, result count, estimated quota units, and clears consecutive errors

#### Scenario: YouTube quota error occurs

- **WHEN** YouTube error has status 403 or 429 and message mentions quota, rate, or exceeded
- **THEN** telemetry marks `quota_exhausted: true`
- **AND** search uses quota backoff for the next sleep

### Requirement: Search loop simplicity

Система SHALL rely on Kubernetes restart policy and PostgreSQL deduplication
instead of an internal supervisor or message bus.

#### Scenario: Search tick raises unexpected error

- **WHEN** one tick fails unexpectedly
- **THEN** worker logs the error and sleeps until the next interval
- **AND** no custom orchestrator is started inside Python
