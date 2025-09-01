from __future__ import annotations

import os
from typing import Any, cast

from yt_dlp import YoutubeDL

from manager.track_queue.models import TrackDict


def build_ydl(cookies_path: str, start: int | None = None, end: int | None = None) -> YoutubeDL:
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "extract_flat": "in_playlist",
        "skip_download": True,
        "socket_timeout": 10,
        "default_search": "ytsearch",
        "cookiefile": cookies_path,
        "sleep_interval_requests": 0.2,
        "max_sleep_interval_requests": 0.6,
    }
    if start is not None:
        opts["playliststart"] = int(start)
    if end is not None:
        opts["playlistend"] = int(end)
    return YoutubeDL(opts)


def search_title_window(title: str, cookies_path: str, start: int, end: int) -> list[TrackDict]:
    """Blocking call executed in a thread: yt_dlp extract window [start .. end] + filtering."""
    if not title.strip():
        return []

    with build_ydl(cookies_path, start, end) as ydl:
        info = ydl.extract_info(f"ytsearch{end}:{title}", download=False)

    entries = cast(list[dict[str, Any]] | None, info.get("entries"))
    if not entries:
        return []

    out: list[TrackDict] = []
    needle = title.lower()

    for e in entries:
        if is_playlist(e) or is_live(e):
            continue

        etitle = str(e.get("title") or "")
        if needle not in etitle.lower():
            continue

        dur = duration_sec(e)
        if dur < 60 or dur > 600:
            continue

        td = to_track_dict(e)
        if td:
            out.append(td)

    return out


def is_playlist(entry: dict[str, Any]) -> bool:
    return entry.get("_type") == "playlist" or str(entry.get("extractor_key", "")).lower().endswith(
        "playlist"
    )


def is_live(entry: dict[str, Any]) -> bool:
    if entry.get("is_live") is True:
        return True
    status = entry.get("live_status")
    return status in {"is_live", "was_live", "is_upcoming"}


def duration_sec(entry: dict[str, Any]) -> int:
    d = entry.get("duration")
    return int(d) if isinstance(d, int | float) else 0


def thumb_url(entry: dict[str, Any]) -> str | None:
    if isinstance(entry.get("thumbnail"), str):
        return cast(str, entry["thumbnail"])
    thumbs = entry.get("thumbnails") or []
    if isinstance(thumbs, list) and thumbs:
        best = max(
            (t for t in thumbs if isinstance(t, dict) and t.get("url")),
            key=lambda t: (t.get("width") or 0) * (t.get("height") or 0),
            default=None,
        )
        if best:
            return cast(str, best.get("url"))
    return None


def to_track_dict(entry: dict[str, Any]) -> TrackDict | None:
    vid = cast(str | None, entry.get("id") or entry.get("video_id"))
    title = cast(str | None, entry.get("title"))
    if not vid or not title:
        return None

    dur = duration_sec(entry)
    channel = cast(str | None, entry.get("channel") or entry.get("uploader"))
    url = cast(str, entry.get("webpage_url") or f"https://www.youtube.com/watch?v={vid}")
    tn = thumb_url(entry)

    return TrackDict(
        youtube_id=vid, title=title, duration_sec=dur, channel=channel, url=url, thumbnail_url=tn
    )


def check_cookies(path: str) -> tuple[bool, str | None]:
    """Return (ok, error). Path must exist, be a file, and be readable."""
    if not path:
        return False, "cookies path is empty"
    if not os.path.exists(path):
        return False, "cookies file does not exist"
    if not os.path.isfile(path):
        return False, "cookies path is not a file"
    if not os.access(path, os.R_OK):
        return False, "cookies file is not readable"
    try:
        if os.path.getsize(path) <= 0:
            return False, "cookies file is empty"
    except OSError as e:
        return False, f"os error: {e}"
    return True, None
