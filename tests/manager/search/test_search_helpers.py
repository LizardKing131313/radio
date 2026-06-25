from __future__ import annotations

import json
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request

import pytest

from manager.search import search_helpers as helpers


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        if isinstance(self._payload, bytes):
            return self._payload
        return json.dumps(self._payload).encode("utf-8")


def _search_item(video_id: str, title: str, live: str = "none") -> dict[str, object]:
    return {
        "id": {"videoId": video_id},
        "snippet": {
            "title": title,
            "channelTitle": "Search Channel",
            "liveBroadcastContent": live,
            "thumbnails": {"default": {"url": "https://thumb/default.jpg"}},
        },
    }


def _video_item(video_id: str, title: str, duration: str) -> dict[str, object]:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "channelTitle": "Detail Channel",
            "thumbnails": {"high": {"url": "https://thumb/high.jpg"}},
        },
        "contentDetails": {"duration": duration},
    }


def test_search_title_window_filters_and_maps(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        {
            "items": [
                _search_item("valid000001", "Govnovoz Track"),
                _search_item("live0000001", "Govnovoz Live", live="live"),
                _search_item("short000001", "Govnovoz Short"),
                _search_item("other000001", "Other Track"),
                {"id": "bad00000001", "snippet": []},
                {"id": {}, "snippet": {"title": "broken"}},
            ],
        },
        {
            "items": [
                _video_item("valid000001", "Govnovoz Track", "PT4M10S"),
                _video_item("live0000001", "Govnovoz Live", "PT4M10S"),
                _video_item("short000001", "Govnovoz Short", "PT30S"),
                _video_item("other000001", "Other Track", "PT4M10S"),
            ],
        },
    ]

    def fake_urlopen(_request: object, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(helpers, "urlopen", fake_urlopen)

    tracks = helpers.search_title_window("govnovoz", "key", 1, 5)

    assert tracks == [
        {
            "youtube_id": "valid000001",
            "title": "Govnovoz Track",
            "duration_sec": 250,
            "channel": "Detail Channel",
            "url": "https://www.youtube.com/watch?v=valid000001",
            "thumbnail_url": "https://thumb/high.jpg",
        }
    ]


def test_search_title_window_handles_pagination(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        {"items": [_search_item("first000001", "Needle One")], "nextPageToken": "next"},
        {"items": [_video_item("first000001", "Needle One", "PT1M1S")]},
        {"items": [_search_item("second00001", "Needle Two")]},
        {"items": [_video_item("second00001", "Needle Two", "PT1M2S")]},
    ]

    monkeypatch.setattr(
        helpers,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse(responses.pop(0)),
    )

    tracks = helpers.search_title_window("needle", "key", 2, 2)

    assert [track["youtube_id"] for track in tracks] == ["second00001"]


def test_search_title_page_uses_token_without_category_filter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses = [
        {
            "items": [_search_item("valid000001", "Needle One")],
            "nextPageToken": "next-token",
        },
        {"items": [_video_item("valid000001", "Needle One", "PT2M")]},
    ]
    seen_queries: list[dict[str, list[str]]] = []

    def fake_urlopen(request: Request, timeout: float) -> FakeResponse:
        assert timeout == 10.0
        seen_queries.append(parse_qs(urlparse(request.full_url).query))
        return FakeResponse(responses.pop(0))

    monkeypatch.setattr(helpers, "urlopen", fake_urlopen)

    page = helpers.search_title_page("needle", "key", 50, "page-token")

    assert [track["youtube_id"] for track in page.tracks] == ["valid000001"]
    assert page.next_page_token == "next-token"
    assert page.raw_count == 1
    assert seen_queries[0]["maxResults"] == ["50"]
    assert seen_queries[0]["pageToken"] == ["page-token"]
    assert "videoCategoryId" not in seen_queries[0]


def test_search_title_window_invalid_inputs() -> None:
    assert helpers.search_title_window("", "key", 1, 1) == []
    assert helpers.search_title_window("title", "", 1, 1) == []
    assert helpers.search_title_window("title", "key", 0, 1) == []
    assert helpers.search_title_window("title", "key", 2, 1) == []
    assert helpers.search_title_page("title", "key", 0) == helpers.SearchPage([], None, 0)


def test_search_title_window_empty_api_page(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        helpers,
        "urlopen",
        lambda *_args, **_kwargs: FakeResponse({"items": []}),
    )

    assert helpers.search_title_window("title", "key", 1, 1) == []


def test_duration_helpers() -> None:
    assert helpers.parse_iso8601_duration("P1DT2H3M4S") == 93784
    assert helpers.parse_iso8601_duration("PT5M") == 300
    assert helpers.parse_iso8601_duration("broken") == 0
    assert helpers.duration_sec({"duration_sec": 1.9}) == 1
    assert helpers.duration_sec({"duration": "PT2S"}) == 2
    assert helpers.duration_sec({}) == 0


def test_thumb_and_track_helpers() -> None:
    assert helpers.thumb_url({"thumbnails": ["bad"]}) is None
    assert helpers.thumb_url({"thumbnails": {"default": {}}}) is None
    assert helpers.thumb_url({"thumbnails": {"default": {"url": "u"}}}) == "u"
    assert helpers.to_track_dict({"id": "", "title": "x"}) is None
    assert helpers.to_track_dict({"id": "id", "title": ""}) is None
    assert helpers.to_track_dict(
        {"id": "id", "title": "Title", "duration_sec": 61, "thumbnails": {}}
    ) == {
        "youtube_id": "id",
        "title": "Title",
        "duration_sec": 61,
        "channel": None,
        "url": "https://www.youtube.com/watch?v=id",
        "thumbnail_url": None,
    }


def test_get_json_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def raise_http(_request: object, timeout: float) -> FakeResponse:
        raise HTTPError("url", 403, "forbidden", Message(), BytesIO(b"quota"))

    monkeypatch.setattr(helpers, "urlopen", raise_http)
    with pytest.raises(helpers.YouTubeAPIError, match="HTTP 403") as error_info:
        helpers._get_json("https://example.test", {"a": "b"})
    assert error_info.value.status_code == 403

    def raise_url(_request: object, timeout: float) -> FakeResponse:
        raise URLError("offline")

    monkeypatch.setattr(helpers, "urlopen", raise_url)
    with pytest.raises(helpers.YouTubeAPIError, match="connection error"):
        helpers._get_json("https://example.test", {"a": "b"})

    monkeypatch.setattr(helpers, "urlopen", lambda *_args, **_kwargs: FakeResponse(b"{"))
    with pytest.raises(helpers.YouTubeAPIError, match="invalid JSON"):
        helpers._get_json("https://example.test", {"a": "b"})

    monkeypatch.setattr(helpers, "urlopen", lambda *_args, **_kwargs: FakeResponse([]))
    with pytest.raises(helpers.YouTubeAPIError, match="non-object"):
        helpers._get_json("https://example.test", {"a": "b"})


def test_private_api_mappers(monkeypatch: pytest.MonkeyPatch) -> None:
    assert helpers._load_video_details("key", []) == {}
    monkeypatch.setattr(
        helpers,
        "_get_json",
        lambda *_args, **_kwargs: {"items": [[], {}, {"id": 5}, {"id": "ok", "snippet": {}}]},
    )
    assert helpers._load_video_details("key", ["ok"]) == {"ok": {"id": "ok", "snippet": {}}}
    assert helpers._entry_from_api_item(
        {"id": {"videoId": "id"}, "snippet": {"title": "Title"}},
        {"snippet": [], "contentDetails": []},
    ) == {
        "id": "id",
        "title": "Title",
        "channel": "",
        "url": "https://www.youtube.com/watch?v=id",
        "thumbnails": {},
        "duration": "",
        "duration_sec": 0,
        "live_broadcast_content": None,
    }
    assert helpers._video_id({"id": "direct"}) == "direct"
    assert helpers._video_id({"id": {"videoId": "nested"}}) == "nested"
    assert helpers._video_id({"id": {}}) is None
    assert helpers._entry_from_api_item({"id": {}, "snippet": {}}, {}) is None
    assert helpers._entry_from_api_item({"id": {"videoId": "id"}}, {}) is None
