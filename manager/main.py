"""Тонкая точка входа для контейнерных команд.

Kubernetes владеет жизненным циклом процессов. Здесь только сопоставление
CLI-команды с конкретным воркером/процессом, который должен жить в контейнере.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from manager.hls import exec_ffmpeg_hls
from manager.logger import configure_logging
from manager.playback.queue_player import QueuePlayer
from manager.prefetch.prefetch import PrefetchWorker
from manager.search.search_service import run_search_loop
from manager.track_queue.db import check_database_schema


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radio-manager")
    parser.add_argument(
        "command",
        choices=["db-check", "search", "prefetch", "queue-player", "ffmpeg-hls"],
    )
    args = parser.parse_args(argv)

    configure_logging()

    try:
        if args.command == "db-check":
            return check_database_schema()
        if args.command == "search":
            asyncio.run(run_search_loop())
            return 0
        if args.command == "prefetch":
            asyncio.run(PrefetchWorker().run_forever())
            return 0
        if args.command == "queue-player":
            asyncio.run(QueuePlayer().run_forever())
            return 0
        if args.command == "ffmpeg-hls":
            return exec_ffmpeg_hls()
    except (KeyboardInterrupt, SystemExit):
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(run(sys.argv[1:]))
