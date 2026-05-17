from __future__ import annotations

import json
import re
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from manager.track_queue.models import TrackDict

YOUTUBE_SEARCH_URL = "https://www.googleapis.com/youtube/v3/search"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

_DURATION_RE = re.compile(
    r"^P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?"
    r"(?:(?P<seconds>\d+)S)?)?$"
)


class YouTubeAPIError(RuntimeError):
    """Ошибка внешнего запроса к YouTube Data API."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


def search_title_window(title: str, api_key: str, start: int, end: int) -> list[TrackDict]:
    """Найти и отфильтровать окно результатов YouTube, нумерация с 1."""
    if not title.strip() or not api_key.strip() or start < 1 or end < start:
        return []

    raw_entries: list[dict[str, Any]] = []
    page_token: str | None = None

    # YouTube search.list отдает только краткие сниппеты. Длительность и часть
    # метаданных добираем отдельным videos.list батчем по найденным id.
    while len(raw_entries) < end:  # pragma: no branch
        page_size = min(50, end - len(raw_entries))
        search_data = _get_json(
            YOUTUBE_SEARCH_URL,
            {
                "part": "snippet",
                "q": title,
                "type": "video",
                "videoCategoryId": "10",
                "maxResults": str(page_size),
                "order": "relevance",
                "safeSearch": "none",
                "key": api_key,
                **({"pageToken": page_token} if page_token else {}),
            },
        )

        items = [item for item in search_data.get("items", []) if isinstance(item, dict)]
        if not items:
            break

        video_ids = [video_id for item in items if (video_id := _video_id(item))]
        details_by_id = _load_video_details(api_key, video_ids)

        for item in items:
            video_id = _video_id(item)
            if video_id is None:
                continue
            entry = _entry_from_api_item(item, details_by_id.get(video_id, {}))
            if entry is not None:
                raw_entries.append(entry)

        page_token = cast(str | None, search_data.get("nextPageToken"))
        if not page_token:
            break

    needle = title.lower()
    out: list[TrackDict] = []
    for entry in raw_entries[start - 1 : end]:
        # В каталог берем только обычные музыкальные ролики разумной длины.
        if is_live(entry):
            continue
        entry_title = str(entry.get("title") or "")
        if needle not in entry_title.lower():
            continue
        duration = duration_sec(entry)
        if duration < 60 or duration > 600:
            continue
        track = to_track_dict(entry)
        if track is not None:  # pragma: no branch
            out.append(track)
    return out


def is_live(entry: dict[str, Any]) -> bool:
    status = str(entry.get("live_broadcast_content") or "").lower()
    return status in {"live", "upcoming"}


def duration_sec(entry: dict[str, Any]) -> int:
    duration = entry.get("duration_sec")
    if isinstance(duration, int):
        return duration
    if isinstance(duration, float):
        return int(duration)
    if isinstance(entry.get("duration"), str):
        return parse_iso8601_duration(str(entry["duration"]))
    return 0


def thumb_url(entry: dict[str, Any]) -> str | None:
    thumbnails = entry.get("thumbnails") or {}
    if not isinstance(thumbnails, dict):
        return None
    # Берем самое качественное превью из доступных стандартных ключей YouTube.
    for key in ("maxres", "standard", "high", "medium", "default"):
        thumbnail = thumbnails.get(key)
        if isinstance(thumbnail, dict) and isinstance(thumbnail.get("url"), str):
            return cast(str, thumbnail["url"])
    return None


def to_track_dict(entry: dict[str, Any]) -> TrackDict | None:
    video_id = cast(str | None, entry.get("id"))
    title = cast(str | None, entry.get("title"))
    if not video_id or not title:
        return None

    return TrackDict(
        youtube_id=video_id,
        title=title,
        duration_sec=duration_sec(entry),
        channel=cast(str | None, entry.get("channel")),
        url=cast(str, entry.get("url") or f"https://www.youtube.com/watch?v={video_id}"),
        thumbnail_url=thumb_url(entry),
    )


def parse_iso8601_duration(value: str) -> int:
    match = _DURATION_RE.match(value)
    if match is None:
        return 0
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def _get_json(url: str, params: dict[str, str], timeout: float = 10.0) -> dict[str, Any]:
    request = Request(f"{url}?{urlencode(params)}", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8")
    except HTTPError as exception:
        detail = exception.read().decode("utf-8", "ignore")
        raise YouTubeAPIError(
            f"YouTube API HTTP {exception.code}: {detail[:300]}",
            status_code=exception.code,
        ) from exception
    except URLError as exception:
        raise YouTubeAPIError(f"YouTube API connection error: {exception}") from exception

    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exception:
        raise YouTubeAPIError("YouTube API returned invalid JSON") from exception
    if not isinstance(parsed, dict):
        raise YouTubeAPIError("YouTube API returned a non-object payload")
    return parsed


def _load_video_details(api_key: str, video_ids: list[str]) -> dict[str, dict[str, Any]]:
    if not video_ids:
        return {}
    # videos.list принимает до 50 id за раз, это совпадает с maxResults search.list.
    data = _get_json(
        YOUTUBE_VIDEOS_URL,
        {
            "part": "contentDetails,snippet",
            "id": ",".join(video_ids[:50]),
            "key": api_key,
        },
    )
    details: dict[str, dict[str, Any]] = {}
    for item in data.get("items", []):
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            details[cast(str, item["id"])] = item
    return details


def _entry_from_api_item(
    search_item: dict[str, Any], details: dict[str, Any]
) -> dict[str, Any] | None:
    video_id = _video_id(search_item)
    snippet = search_item.get("snippet")
    if video_id is None or not isinstance(snippet, dict):
        return None

    details_snippet = details.get("snippet")
    if not isinstance(details_snippet, dict):
        details_snippet = {}
    content_details = details.get("contentDetails")
    if not isinstance(content_details, dict):
        content_details = {}

    duration = str(content_details.get("duration") or "")
    return {
        "id": video_id,
        "title": str(details_snippet.get("title") or snippet.get("title") or ""),
        "channel": str(details_snippet.get("channelTitle") or snippet.get("channelTitle") or ""),
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnails": details_snippet.get("thumbnails") or snippet.get("thumbnails") or {},
        "duration": duration,
        "duration_sec": parse_iso8601_duration(duration),
        "live_broadcast_content": snippet.get("liveBroadcastContent"),
    }


def _video_id(item: dict[str, Any]) -> str | None:
    item_id = item.get("id")
    if isinstance(item_id, dict) and isinstance(item_id.get("videoId"), str):
        return cast(str, item_id["videoId"])
    if isinstance(item_id, str):
        return item_id
    return None
