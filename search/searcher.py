from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL


BASE_DIR = Path(__file__).resolve().parent
_YDL_HOME = BASE_DIR / "_ydl"
(_YDL_HOME / "tmp").mkdir(parents=True, exist_ok=True)
(_YDL_HOME / "cache").mkdir(parents=True, exist_ok=True)


class _SilentLogger:
    def debug(self, msg: str) -> None: ...
    def warning(self, msg: str) -> None: ...
    def error(self, msg: str) -> None: ...


def _ydl_opts() -> dict[str, object]:
    return {
        "quiet": True,
        "no_warnings": True,
        "logger": _SilentLogger(),
        "skip_download": True,
        "extract_flat": True,
        "format": "bestaudio/best",
        "cachedir": False,
        "paths": {
            "home": str(_YDL_HOME),
            "temp": str(_YDL_HOME / "tmp"),
        },
        "writedescription": False,
        "writethumbnail": False,
        "writeinfojson": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "writecomments": False,
        "noprogress": True,
        "nocolor": True,
    }


def _resolve_video_card(ydl: YoutubeDL, entry: dict[str, Any]) -> dict[str, Any] | None:
    if entry.get("webpage_url") and entry.get("duration") is not None:
        return entry

    video_id_or_url: str | None = entry.get("url")
    if not video_id_or_url:
        return None

    target_url = (
        video_id_or_url
        if isinstance(video_id_or_url, str) and video_id_or_url.startswith("http")
        else f"https://www.youtube.com/watch?v={video_id_or_url}"
    )
    # noinspection PyBroadException
    try:
        return ydl.extract_info(target_url, download=False)
    except Exception:
        return None


def search_queries(queries: list[str], per_query: int = 50) -> Iterator[dict[str, Any]]:
    with YoutubeDL(_ydl_opts()) as ydl:
        for q in queries:
            res: dict[str, Any] = ydl.extract_info(f"ytsearch{per_query}:{q}", download=False)
            for e in res.get("entries", []) or []:
                card = _resolve_video_card(ydl, e)
                if card:
                    yield card


def list_channel(url: str) -> Iterator[dict[str, Any]]:
    return execute_ydl(url)


def list_playlist(url: str) -> Iterator[dict[str, Any]]:
    return list_channel(url)


def list_hashtag(tag: str, per_page: int = 0) -> Iterator[dict[str, Any]]:
    url = f"https://www.youtube.com/hashtag/{tag.lstrip('#')}"
    return execute_ydl(url)


def execute_ydl(url: str) -> Iterator[dict[str, Any]]:
    with YoutubeDL(_ydl_opts()) as ydl:
        res: dict[str, Any] = ydl.extract_info(url, download=False)
        for e in res.get("entries", []) or []:
            card = _resolve_video_card(ydl, e)
            if card:
                yield card
