from __future__ import annotations

import asyncio
from functools import cached_property

from structlog.typing import FilteringBoundLogger

from manager.config import AppConfig, get_settings
from manager.runner.control import ControlMessage, ControlNode, ControlResult, Success
from manager.runner.node import Action
from manager.runner.process_runnable import ProcessCommand, ProcessRunnable


class HLS(ProcessRunnable):
    def __init__(self, node_id: ControlNode, config: AppConfig | None = None) -> None:
        super().__init__(node_id=node_id)
        self.node_id = node_id
        self.config = config or get_settings()

    # fmt: off
    @cached_property
    def command(self) -> ProcessCommand:
        return ProcessCommand(
            exe="/usr/bin/ffmpeg",
            args=[
                "-nostdin", "-hide_banner", "-loglevel", "warning",
                "-i", str(self.config.paths.fifo_audio_path),

                # --- TS ---
                *self._build_audio_args(),
                "-f", "hls",
                "-hls_time", str(self.config.hls.hls_time),
                "-hls_list_size", str(self.config.hls.hls_list_size),
                "-hls_delete_threshold", str(self.config.hls.hls_delete_threshold),
                "-hls_flags", "independent_segments+append_list+delete_segments",
                "-hls_start_number_source", "epoch",
                "-master_pl_name", "playlist.m3u8",
                "-var_stream_map",  self._stream_map(),
                "-hls_segment_type", "mpegts",
                "-hls_segment_filename",
                str(self.config.paths.www_hls_ts / "v%v" / "seg_%05d.ts"),
                str(self.config.paths.www_hls_ts / "v%v" / "index.m3u8"),

                # --- CMAF ---
                *self._build_audio_args(),
                "-f", "hls",
                "-hls_time", str(self.config.hls.hls_time),
                "-hls_list_size", str(self.config.hls.hls_list_size),
                "-hls_delete_threshold", str(self.config.hls.hls_delete_threshold),
                "-hls_flags", "independent_segments+omit_endlist+append_list+delete_segments",
                "-hls_start_number_source", "epoch",
                "-master_pl_name", "playlist.m3u8",
                "-var_stream_map", self._stream_map(),
                "-hls_segment_type", "fmp4",
                "-hls_fmp4_init_filename", "init.mp4",
                "-hls_segment_filename",
                str(self.config.paths.www_hls_mp4 / "v%v" / "seg_%05d.m4s"),
                str(self.config.paths.www_hls_mp4 / "v%v" / "index.m3u8"),
            ]
    )
    # fmt: on

    def _stream_map(self) -> str:
        return " ".join(
            f"a:{i},name:{bitrate}k" for i, bitrate in enumerate(self.config.hls.bitrates)
        )

    # fmt: off
    def _build_audio_args(self) -> list[str]:
        return [
            arg
            for i, bitrate in enumerate(self.config.hls.bitrates)
            for arg in (
                "-map", "0:a",
                f"-c:a:{i}", "aac",
                f"-b:a:{i}", f"{bitrate}k",
                f"-ar:{i}", "44100",
                f"-ac:{i}", "2",
            )

        ]
    # fmt: on

    def get_ready_action(self) -> Action | None:
        async def _run() -> ControlResult:
            return Success("OK")

        return _run

    async def check(
        self, ready_event: asyncio.Event, log_event: FilteringBoundLogger
    ) -> ControlResult:
        return Success("OK")

    async def receive(
        self, ready_event: asyncio.Event, message: ControlMessage, log_event: FilteringBoundLogger
    ) -> ControlResult:
        pass
