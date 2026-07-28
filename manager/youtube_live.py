from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from manager.search.search_helpers import YouTubeAPIError

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"


def live_refresh_interval(refresh_sec: int) -> int:
    return max(1, refresh_sec)


def live_refresh_due(video_id: str, now: float, next_refresh: float) -> bool:
    return bool(video_id) and now >= next_refresh


def empty_live_state(status: str = "disabled") -> dict[str, object]:
    return {
        "status": status,
        "video_id": None,
        "title": None,
        "channel": None,
        "broadcast_status": None,
        "scheduled_start_time": None,
        "actual_start_time": None,
        "actual_end_time": None,
        "updated_at": None,
        "last_success_at": None,
        "last_error": None,
    }


def read_live_state(path: Path) -> dict[str, object]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty_live_state("unknown")
    except (OSError, json.JSONDecodeError):
        return empty_live_state("unreadable")
    return (
        {**empty_live_state(), **raw} if isinstance(raw, dict) else empty_live_state("unreadable")
    )


def fetch_live_metadata(video_id: str, api_key: str) -> dict[str, object]:
    query = urlencode(
        {"part": "snippet,liveStreamingDetails,status", "id": video_id, "key": api_key}
    )
    request = Request(f"{YOUTUBE_VIDEOS_URL}?{query}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise YouTubeAPIError(f"YouTube live metadata request failed: {exc}") from exc
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        raise YouTubeAPIError(f"YouTube live video not found: {video_id}")
    item = items[0]
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    details = (
        item.get("liveStreamingDetails")
        if isinstance(item.get("liveStreamingDetails"), dict)
        else {}
    )
    status = item.get("status") if isinstance(item.get("status"), dict) else {}
    return {
        "status": "ok",
        "video_id": video_id,
        "title": snippet.get("title"),
        "channel": snippet.get("channelTitle"),
        "broadcast_status": snippet.get("liveBroadcastContent") or status.get("uploadStatus"),
        "scheduled_start_time": details.get("scheduledStartTime"),
        "actual_start_time": details.get("actualStartTime"),
        "actual_end_time": details.get("actualEndTime"),
        "updated_at": datetime.now(UTC).isoformat(),
        "last_success_at": datetime.now(UTC).isoformat(),
        "last_error": None,
    }


def refresh_live_metadata(path: Path, video_id: str, api_key: str) -> dict[str, object]:
    previous = read_live_state(path)
    try:
        state = fetch_live_metadata(video_id, api_key)
    except YouTubeAPIError as exc:
        state = {
            **previous,
            "status": "stale",
            "last_error": str(exc),
            "updated_at": datetime.now(UTC).isoformat(),
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    temporary.replace(path)
    return state
