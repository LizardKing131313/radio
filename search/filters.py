from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def _parse_upload_date_yyyymmdd(raw: str) -> datetime | None:
    # noinspection PyBroadException
    try:
        return datetime.strptime(raw, "%Y%m%d")
    except Exception:
        return None


def _parse_iso_date(raw: str) -> datetime | None:
    # noinspection PyBroadException
    try:
        return datetime.fromisoformat(raw)
    except Exception:
        return None


def _is_short(item: dict[str, Any], exclude_shorts: bool) -> bool:
    if not exclude_shorts:
        return False
    url = str(item.get("webpage_url") or "")
    if "/shorts/" in url:
        return True
    dur = item.get("duration")
    return bool(isinstance(dur, int | float) and dur <= 61)


def _is_music(item: dict[str, Any]) -> bool:
    cats = item.get("categories") or []
    if isinstance(cats, list) and any(str(c).lower() == "music" for c in cats):
        return True
    if item.get("artist") or item.get("track"):
        return True
    title = (item.get("title") or "").lower()
    if "cover" in title or "кавер" in title:
        return True
    return str(item.get("genre") or "").lower() in {"music", "electronic", "pop", "rock"}


_AI_PAT = re.compile(
    r"(?i)\b(ai|a\.i\.|искусственн|нейро|нейросет|генерир|suno|cover\s*ai|ai\s*cover|ai\s*vocal|ai\s*voice)\b|#ai|#нейро|#искусственный",
    re.UNICODE,
)


def _has_ai_marker(item: dict[str, Any]) -> bool:
    hay = ((item.get("title") or "") + "\n" + (item.get("description") or "")).lower()
    return bool(_AI_PAT.search(hay))


_ORIG_LINK_DOMAINS = (
    "youtube.com/watch",
    "music.youtube",
    "open.spotify.com",
    "music.yandex",
    "vk.com/music",
    "apple.com/music",
    "soundcloud.com",
    "bandcamp.com",
    "deezer.com",
)


def _mentions_original_artist(item: dict[str, Any]) -> bool:
    if item.get("artist") or item.get("track"):
        return True
    desc = item.get("description") or ""
    title = item.get("title") or ""
    hay = f"{title}\n{desc}".lower()
    if any(d in desc.lower() for d in _ORIG_LINK_DOMAINS):
        return True
    if (" cover" in hay or " кавер" in hay) and (" - " in title or " — " in title):
        return True
    return bool(any(k in hay for k in ("original", "оригинал", "by ", "автор ", "исполнитель ")))


def _has_tag(item: dict[str, Any], tag: str | None) -> bool:
    if not tag:
        return True
    tags = item.get("tags") or []
    tag_l = tag.lstrip("#").lower()
    if isinstance(tags, list) and any(str(t).lower() == tag_l for t in tags):
        return True
    hay = ((item.get("title") or "") + "\n" + (item.get("description") or "")).lower()
    return f"#{tag_l}" in hay


def _title_contains_any(item: dict[str, Any], substrings: list[str] | None) -> bool:
    if not substrings:
        return False
    title = (item.get("title") or "").lower()
    return any(s.lower() in title for s in substrings if s)


def pass_filters(
    item: dict[str, Any],
    *,
    min_d: int,
    max_d: int,
    min_views: int,
    date_after: str,
    blacklist_rx: str,
    exclude_shorts: bool = False,
    require_music: bool = False,
    require_ai_marker: bool = False,
    require_artist_ref: bool = False,
    required_tag: str | None = None,
    title_any: list[str] | None = None,
    tag_or_title: bool = False,
) -> bool:
    return not explain_filters(
        item,
        min_d=min_d,
        max_d=max_d,
        min_views=min_views,
        date_after=date_after,
        blacklist_rx=blacklist_rx,
        exclude_shorts=exclude_shorts,
        require_music=require_music,
        require_ai_marker=require_ai_marker,
        require_artist_ref=require_artist_ref,
        required_tag=required_tag,
        title_any=title_any,
        tag_or_title=tag_or_title,
    )


def explain_filters(
    item: dict[str, Any],
    *,
    min_d: int,
    max_d: int,
    min_views: int,
    date_after: str,
    blacklist_rx: str,
    exclude_shorts: bool = False,
    require_music: bool = False,
    require_ai_marker: bool = False,
    require_artist_ref: bool = False,
    required_tag: str | None = None,
    title_any: list[str] | None = None,
    tag_or_title: bool = False,
) -> list[str]:
    reasons: list[str] = []

    dur = item.get("duration")
    if not isinstance(dur, int | float) or dur < min_d or dur > max_d:
        reasons.append("duration_out_of_range")

    if bool(item.get("is_live")):
        reasons.append("is_live")

    views = item.get("view_count")
    # noinspection PyBroadException
    try:
        if int(views or 0) < min_views:
            reasons.append("views_below_min")
    except Exception:
        reasons.append("views_invalid")

    if date_after:
        after_dt = _parse_iso_date(date_after)
        ymd_raw = item.get("upload_date")
        up_dt = _parse_upload_date_yyyymmdd(ymd_raw) if isinstance(ymd_raw, str) else None
        if after_dt is None or up_dt is None or up_dt < after_dt:
            reasons.append("date_before_after")

    title = (item.get("title") or "").strip()
    if blacklist_rx:
        try:
            if re.search(blacklist_rx, title):
                reasons.append("title_blacklist")
        except re.error:
            pass

    if exclude_shorts and _is_short(item, True):
        reasons.append("shorts")

    title_ok = _title_contains_any(item, title_any)
    tag_ok = _has_tag(item, required_tag)
    if tag_or_title:
        if not (tag_ok or title_ok):
            reasons.append("tag_or_title_missing")
    else:
        if required_tag and not tag_ok:
            reasons.append("tag_missing")

    if require_music and not _is_music(item):
        reasons.append("not_music")

    if require_ai_marker and not _has_ai_marker(item):
        reasons.append("no_ai_marker")

    if require_artist_ref and not _mentions_original_artist(item):
        reasons.append("no_artist_ref")

    return reasons
