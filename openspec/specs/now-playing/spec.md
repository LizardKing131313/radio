## Purpose

Фиксирует расчет текущего эфира для API. Источник правды для текущего трека -
файлы Liquidsoap `nowplaying.txt` и `nowplaying.txt.kv` плюс расчетный HLS lag.

## Requirements

### Requirement: Liquidsoap metadata reading

Система SHALL читать current metadata из plain nowplaying file и optional KV
file written by Liquidsoap.

#### Scenario: KV and plain files exist

- **WHEN** `nowplaying.txt` и `nowplaying.txt.kv` доступны
- **THEN** snapshot contains title, artist, album, display line, and updated timestamp

#### Scenario: Metadata files are missing

- **WHEN** nowplaying files отсутствуют
- **THEN** snapshot returns `source: null`
- **AND** HLS offset fields remain present

### Requirement: HLS audible estimate

Система MUST calculate estimated audible time from metadata mtime and configured
HLS segment settings.

#### Scenario: Metadata is newer than audible edge

- **WHEN** current time is before `updated_at + live_offset_sec`
- **THEN** `is_probably_audible` is false

#### Scenario: Metadata passed audible edge

- **WHEN** current time is at or after `updated_at + live_offset_sec`
- **THEN** `is_probably_audible` is true

### Requirement: Stable HLS offset bounds

Система SHALL compute live offset as `hls_time * min(hls_list_size, 3)` with
minimum values of one segment and one second.

#### Scenario: Normal HLS config

- **WHEN** `hls_time=6` and `hls_list_size=12`
- **THEN** `live_offset_sec` is `18`

#### Scenario: Invalid low values are configured

- **WHEN** HLS time or list size is below one
- **THEN** offset calculation still returns a positive value
