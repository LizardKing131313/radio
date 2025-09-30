from __future__ import annotations

import asyncio
import os
import sys
from functools import cached_property
from typing import ClassVar

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.runner.control import ControlMessage, ControlNode, ControlResult, Success
from manager.runner.node import Action
from manager.runner.process_runnable import ProcessCommand, ProcessRunnable


class HLS(ProcessRunnable):
    health_interval_sec: ClassVar[float] = 10.0

    def __init__(self, node_id: ControlNode, config: AppConfig | None = None) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self._config = config or get_settings()

    # fmt: off
    @cached_property
    def command(self) -> ProcessCommand:
        return ProcessCommand(
            exe="/usr/bin/ffmpeg",
            args=[
                "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-i", str(self._config.paths.fifo_audio_path),

                # --- TS ---
                *self._build_audio_args(),
                "-f", "hls",
                "-hls_time", str(self._config.hls.hls_time),
                "-hls_list_size", str(self._config.hls.hls_list_size),
                "-hls_delete_threshold", str(self._config.hls.hls_delete_threshold),
                "-hls_flags", "independent_segments+append_list+delete_segments",
                "-hls_start_number_source", "epoch",
                "-master_pl_name", "playlist.m3u8",
                "-var_stream_map",  self._stream_map(),
                "-hls_segment_type", "mpegts",
                "-hls_segment_filename",
                str(self._config.paths.www_hls_ts / "v%v" / "seg_%05d.ts"),
                str(self._config.paths.www_hls_ts / "v%v" / "index.m3u8"),

                # --- CMAF ---
                *self._build_audio_args(),
                "-f", "hls",
                "-hls_time", str(self._config.hls.hls_time),
                "-hls_list_size", str(self._config.hls.hls_list_size),
                "-hls_delete_threshold", str(self._config.hls.hls_delete_threshold),
                "-hls_flags", "independent_segments+omit_endlist+append_list+delete_segments",
                "-hls_start_number_source", "epoch",
                "-master_pl_name", "playlist.m3u8",
                "-var_stream_map", self._stream_map(),
                "-hls_segment_type", "fmp4",
                "-hls_fmp4_init_filename", "init.mp4",
                "-hls_segment_filename",
                str(self._config.paths.www_hls_mp4 / "v%v" / "seg_%05d.m4s"),
                str(self._config.paths.www_hls_mp4 / "v%v" / "index.m3u8"),
            ]
    )
    # fmt: on

    def _stream_map(self) -> str:
        return " ".join(
            f"a:{i},name:{bitrate}k" for i, bitrate in enumerate(self._config.hls.bitrates)
        )

    # fmt: off
    def _build_audio_args(self) -> list[str]:
        return [
            arg
            for i, bitrate in enumerate(self._config.hls.bitrates)
            for arg in (
                "-map", "0:a",
                f"-c:a:{i}", "aac",
                f"-b:a:{i}", f"{bitrate}k",
                f"-ar:{i}", "44100",
                f"-ac:{i}", "2",
            )

        ]
    # fmt: on

    def _get_ready_action(self) -> Action | None:
        fifo_path = str(self._config.paths.fifo_audio_path)

        async def _run() -> ControlResult:
            # Do not poke FIFO writer-side here at all.
            if not os.path.exists(fifo_path):
                return Success(f"FIFO not found yet: {fifo_path}")
            # Consider HLS 'ready' when ffmpeg process is up; runner already tracks proc.started.
            return Success("HLS ready check: skipped destructive FIFO probe.")

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        fifo_path = str(self._config.paths.fifo_audio_path)
        # Safe, non-destructive probe:
        # open read end NONBLOCK just to ensure FIFO exists and is accessible.
        try:
            file_descriptor = self._open(fifo_path)
            os.close(file_descriptor)
            return Success("OK: FIFO accessible (non-blocking read).")
        except OSError as exception:
            # Still do not fail the node here; just report.
            return Success(f"NOTE: FIFO read-probe errno={exception.errno} ({exception.strerror})")

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        pass

    @staticmethod
    def _open(fifo_path: str) -> int:
        if sys.platform != "win32":
            return os.open(fifo_path, os.O_RDONLY | os.O_NONBLOCK)
        else:
            raise NotImplementedError(f"sys.platform == '{sys.platform}'")
