from __future__ import annotations

import os

from manager.config import AppConfig, get_settings


def build_ffmpeg_hls_args(config: AppConfig) -> list[str]:
    # Один ffmpeg читает FIFO и одновременно пишет TS и fMP4 HLS-варианты.
    audio_args = _build_audio_args(config)
    return [
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-i",
        str(config.paths.fifo_audio_path),
        *audio_args,
        "-f",
        "hls",
        "-hls_time",
        str(config.hls.hls_time),
        "-hls_list_size",
        str(config.hls.hls_list_size),
        "-hls_delete_threshold",
        str(config.hls.hls_delete_threshold),
        "-hls_flags",
        "independent_segments+append_list+delete_segments",
        "-hls_start_number_source",
        "epoch",
        "-master_pl_name",
        "playlist.m3u8",
        "-var_stream_map",
        _stream_map(config),
        "-hls_segment_type",
        "mpegts",
        "-hls_segment_filename",
        str(config.paths.www_hls_ts / "v%v" / "seg_%05d.ts"),
        str(config.paths.www_hls_ts / "v%v" / "index.m3u8"),
        *audio_args,
        "-f",
        "hls",
        "-hls_time",
        str(config.hls.hls_time),
        "-hls_list_size",
        str(config.hls.hls_list_size),
        "-hls_delete_threshold",
        str(config.hls.hls_delete_threshold),
        "-hls_flags",
        "independent_segments+omit_endlist+append_list+delete_segments",
        "-hls_start_number_source",
        "epoch",
        "-master_pl_name",
        "playlist.m3u8",
        "-var_stream_map",
        _stream_map(config),
        "-hls_segment_type",
        "fmp4",
        "-hls_fmp4_init_filename",
        "init.mp4",
        "-hls_segment_filename",
        str(config.paths.www_hls_mp4 / "v%v" / "seg_%05d.m4s"),
        str(config.paths.www_hls_mp4 / "v%v" / "index.m3u8"),
    ]


def exec_ffmpeg_hls(config: AppConfig | None = None) -> int:
    cfg = config or get_settings()
    _ensure_hls_dirs(cfg)
    args = ["ffmpeg", *build_ffmpeg_hls_args(cfg)]
    # Заменяем Python на ffmpeg, чтобы Kubernetes видел реальный exit процесса.
    os.execvp(args[0], args)
    return 1


def _stream_map(config: AppConfig) -> str:
    # FFmpeg ожидает карту аудио-потоков одной строкой: "a:0,name:64k ...".
    return " ".join(
        f"a:{index},name:{bitrate}k" for index, bitrate in enumerate(config.hls.bitrates)
    )


def _build_audio_args(config: AppConfig) -> list[str]:
    return [
        arg
        for index, bitrate in enumerate(config.hls.bitrates)
        for arg in (
            "-map",
            "0:a",
            f"-c:a:{index}",
            "aac",
            f"-b:a:{index}",
            f"{bitrate}k",
            f"-ar:{index}",
            "44100",
            f"-ac:{index}",
            "2",
        )
    ]


def _ensure_hls_dirs(config: AppConfig) -> None:
    # FFmpeg не создает вложенные variant-директории сам.
    for bitrate in config.hls.bitrates:
        (config.paths.www_hls_ts / f"v{bitrate}k").mkdir(parents=True, exist_ok=True)
        (config.paths.www_hls_mp4 / f"v{bitrate}k").mkdir(parents=True, exist_ok=True)
