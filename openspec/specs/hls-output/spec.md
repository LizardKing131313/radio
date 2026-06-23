## Purpose

Фиксирует поведение FFmpeg HLS слоя. Python только собирает аргументы и
создает директории, после чего процесс должен быть настоящим `ffmpeg`.

## Requirements

### Requirement: FFmpeg argument assembly

Система SHALL строить FFmpeg arguments из `AppConfig` без запуска subprocess
supervisor внутри Python.

#### Scenario: HLS args are built

- **WHEN** `build_ffmpeg_hls_args` получает config
- **THEN** args читают audio из `paths.fifo_audio_path`
- **AND** args содержат TS output и fMP4 output
- **AND** каждый bitrate из `hls.bitrates` получает отдельный audio mapping

### Requirement: Variant directory preparation

Система MUST создавать вложенные variant directories перед exec FFmpeg.

#### Scenario: FFmpeg output starts

- **WHEN** `exec_ffmpeg_hls` запускается
- **THEN** директории `www_hls_ts/v<bitrate>k` и `www_hls_mp4/v<bitrate>k` существуют
- **AND** FFmpeg может писать playlist и segment files

### Requirement: Process replacement

Python wrapper SHALL replace itself with `ffmpeg` so Kubernetes observes the
real media process lifecycle.

#### Scenario: Exec succeeds

- **WHEN** `exec_ffmpeg_hls` reaches process start
- **THEN** it calls `os.execvp` with command `ffmpeg`
- **AND** no Python loop supervises the child process

### Requirement: Dual HLS output

The HLS layer SHALL produce both MPEG-TS and fragmented MP4 playlists from the
same FIFO audio input.

#### Scenario: Client needs TS stream

- **WHEN** a client requests TS HLS output through Nginx
- **THEN** FFmpeg has written TS variant playlists under `www_hls_ts`

#### Scenario: Client needs fMP4 stream

- **WHEN** a client requests fMP4 HLS output through Nginx
- **THEN** FFmpeg has written fMP4 variant playlists under `www_hls_mp4`
