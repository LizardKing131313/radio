from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr

from manager.api.app import app, get_database, require_admin_token
from manager.config import AppConfig, get_settings
from manager.track_queue.db import Database
from manager.track_queue.models import Track
from manager.track_queue.orm import Base
from manager.track_queue.repo import OffersRepo, QueueRepo, TracksRepo


def _patch_api_settings(monkeypatch: pytest.MonkeyPatch, cfg: AppConfig) -> None:
    for module_name in (
        "manager.api.dependencies",
        "manager.api.routes",
        "manager.api.web",
    ):
        monkeypatch.setattr(import_module(module_name), "get_settings", lambda: cfg)


@pytest.fixture
def api_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Database]]:
    dsn = f"sqlite+pysqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("RADIO_DATABASE_DSN", dsn)
    monkeypatch.setenv("RADIO_ADMIN_TOKEN", "secret-token")
    get_settings.cache_clear()

    cfg = AppConfig()
    cfg.paths.www_html = tmp_path / "www" / "html"
    cfg.paths.nowplaying_path = tmp_path / "runtime" / "nowplaying.txt"
    cfg.paths.nowplaying_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.secrets.admin_token_raw = SecretStr("secret-token")
    _write_web_build(cfg.paths.www_html)
    _patch_api_settings(monkeypatch, cfg)

    database = Database(app_config=cfg, dsn=dsn)
    Base.metadata.create_all(database.engine)

    app.dependency_overrides[get_database] = lambda: database
    try:
        with TestClient(app) as client:
            yield client, database
    finally:
        app.dependency_overrides.clear()
        database.close()
        get_settings.cache_clear()


def _write_web_build(root: Path) -> None:
    (root / "apps" / "player").mkdir(parents=True, exist_ok=True)
    (root / "apps" / "admin").mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    (root / "icons").mkdir(exist_ok=True)
    (root / "apps" / "player" / "index.html").write_text(
        '<!doctype html><html><body data-radio-app="player">Player</body></html>',
        encoding="utf-8",
    )
    (root / "apps" / "admin" / "index.html").write_text(
        '<!doctype html><html><body data-radio-app="admin">Radio Admin</body></html>',
        encoding="utf-8",
    )
    (root / "assets" / "player-abc123.js").write_text(
        "console.log('player');",
        encoding="utf-8",
    )
    (root / "manifest.webmanifest").write_text(
        '{"name":"Radio Player","start_url":"/player","display":"standalone"}',
        encoding="utf-8",
    )
    (root / "sw.js").write_text(
        "self.addEventListener('fetch', () => {});",
        encoding="utf-8",
    )
    (root / "favicon.svg").write_text("<svg />", encoding="utf-8")
    (root / "icons" / "icon-192.svg").write_text("<svg />", encoding="utf-8")


def _write_queue_metadata(
    cfg: AppConfig,
    *,
    queue_id: int | None,
    track_id: int | None,
    queue_kind: str | None = None,
) -> None:
    cfg.paths.nowplaying_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.paths.nowplaying_path.with_name(cfg.paths.nowplaying_path.name + ".kv").write_text(
        f"queue_id={queue_id or ''}\ntrack_id={track_id or ''}\nqueue_kind={queue_kind or ''}\n",
        encoding="utf-8",
    )


def test_web_client_routes_assets_and_api_namespace(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _database = api_context

    player = client.get("/player")
    assert player.status_code == 200
    assert "text/html" in player.headers["content-type"]
    assert player.headers["cache-control"] == "no-cache"
    assert 'data-radio-app="player"' in player.text
    assert client.get("/").text == player.text
    assert client.get("/player/settings").text == player.text

    admin = client.get("/admin")
    assert admin.status_code == 200
    assert admin.headers["cache-control"] == "no-store"
    assert 'data-radio-app="admin"' in admin.text
    assert "secret-token" not in admin.text

    asset = client.get("/assets/player-abc123.js")
    assert asset.status_code == 200
    assert "javascript" in asset.headers["content-type"]
    assert asset.headers["cache-control"] == "public,max-age=31536000,immutable"

    manifest = client.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert "application/manifest+json" in manifest.headers["content-type"]
    assert manifest.json()["start_url"] == "/player"

    service_worker = client.get("/sw.js")
    assert service_worker.status_code == 200
    assert "javascript" in service_worker.headers["content-type"]
    assert service_worker.headers["cache-control"] == "no-cache"

    favicon = client.get("/favicon.svg")
    assert favicon.status_code == 200
    assert favicon.headers["content-type"].startswith("image/svg+xml")

    assert client.get("/icons/icon-192.svg").status_code == 200
    assert client.get("/api/current").status_code == 404
    assert client.get("/current").headers["content-type"].startswith("application/json")

    api_module = import_module("manager.api.app")
    with pytest.raises(HTTPException):
        api_module._safe_web_path(tmp_path / "assets", "../manifest.webmanifest")

    cfg = AppConfig()
    cfg.paths.www_html = tmp_path / "missing-web-build"
    _patch_api_settings(monkeypatch, cfg)
    assert client.get("/player").status_code == 503
    assert client.get("/assets/missing.js").status_code == 404


def test_queued_play_uri_without_queue_kind() -> None:
    api_module = import_module("manager.api.routes")
    uri = api_module.queued_play_uri(
        12,
        Track(
            id=34,
            youtube_id="youtube0001",
            title="Track",
            duration_sec=120,
            url="https://youtu.be/youtube0001",
        ),
        Path("cache") / "track.opus",
    )

    assert uri == 'annotate:queue_id="12",track_id="34":cache/track.opus'
    assert "queue_kind" not in uri


def test_health_queue_current_and_admin_enqueue(api_context: tuple[TestClient, Database]) -> None:
    client, database = api_context
    request = Request(
        {"type": "http", "app": SimpleNamespace(state=SimpleNamespace(database=database))}
    )
    assert get_database(request) is database

    tracks = TracksRepo(database)
    queue = QueueRepo(database)
    track_id = tracks.upsert("youtube0001", "Track", 120)

    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["youtube_api"]["status"] == "unknown"
    assert client.get("/current").json() == {
        "now_playing": {
            "source": None,
            "hls": {
                "live_offset_sec": 6,
                "age_sec": None,
                "estimated_audible_at": None,
                "is_probably_audible": False,
            },
        },
        "queue": None,
    }
    assert client.post("/queue/append", json={"track_id": track_id}).status_code == 401

    headers = {"Authorization": "Bearer secret-token"}
    append_response = client.post(
        "/queue/append",
        json={"track_id": track_id, "requested_by": "user", "note": "note"},
        headers=headers,
    )
    assert append_response.status_code == 200
    queue_id = append_response.json()["queue_id"]
    queue.mark_playing(queue_id)

    current = client.get("/current").json()["queue"]
    assert current["queue_item"]["id"] == queue_id
    assert current["track"]["id"] == track_id
    assert client.get("/queue?limit=1").json()["items"][0]["queue_item"]["id"] == queue_id

    next_response = client.post(
        "/queue/append/admin",
        json={"track_id": track_id},
        headers=headers,
    )
    assert next_response.status_code == 200
    assert next_response.json()["queue_id"] > queue_id

    metrics = client.get("/metrics").json()
    assert metrics["status"] == "ok"
    assert metrics["tracks"]["active"] == 1
    assert metrics["queue"]["visible"][0]["queue_item"]["id"] == queue_id

    prometheus = client.get("/metrics/prometheus")
    assert prometheus.status_code == 200
    assert "text/plain" in prometheus.headers["content-type"]
    assert 'radio_tracks_total{status="active"} 1' in prometheus.text
    assert "radio_queue_visible_items 2" in prometheus.text
    assert "radio_youtube_quota_exhausted 0" in prometheus.text
    assert "radio_hls_live_offset_seconds 6" in prometheus.text


def test_offer_endpoints_and_admin_actions(api_context: tuple[TestClient, Database]) -> None:
    client, database = api_context
    track_id = TracksRepo(database).upsert("youtube0001", "Track", 120)
    headers = {"Authorization": "Bearer secret-token"}

    add_response = client.post(
        "/offers/add",
        json={"youtube_url": "https://youtu.be/x", "submitted_by": "user", "note": "note"},
    )
    assert add_response.status_code == 200
    offer_id = add_response.json()["offer_id"]

    assert client.get("/offers?status=new").json()["items"][0]["id"] == offer_id
    assert client.get(f"/offers/{offer_id}").json()["youtube_url"] == "https://youtu.be/x"
    assert client.get("/offers/404").status_code == 404

    accept_response = client.post(
        f"/offers/{offer_id}/accept",
        json={"track_id": track_id},
        headers=headers,
    )
    assert accept_response.json() == {"status": "accepted"}
    assert OffersRepo(database).get(offer_id).accepted_track_id == track_id

    cancelled_id = OffersRepo(database).add("https://youtu.be/y")
    cancel_response = client.post(f"/offers/{cancelled_id}/cancel", headers=headers)
    assert cancel_response.json() == {"status": "cancelled"}
    assert OffersRepo(database).get(cancelled_id).status == "cancelled"


def test_queue_skip_endpoint(
    api_context: tuple[TestClient, Database],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    headers = {"Authorization": "Bearer secret-token"}
    track_id = TracksRepo(database).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(database)
    queue_id = queue.enqueue(track_id)
    queue.mark_playing(queue_id)
    calls: list[str] = []
    routes_module = import_module("manager.api.routes")
    cfg = routes_module.get_settings()
    _write_queue_metadata(cfg, queue_id=queue_id, track_id=track_id)

    class FakeTelnet:
        def skip_output(self) -> str:
            calls.append("output-skip")
            return "Done"

        def skip_request_queue(self) -> str:
            calls.append("request-skip")
            return "Done"

        def skip_play_now(self) -> str:
            calls.append("play-now-skip")
            return "Done"

        def skip_library_sources(self) -> list[str]:
            calls.append("library-skip")
            return ["Done", "Done"]

        def flush_request_queue(self) -> str:
            calls.append("flush")
            return "Done"

    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["request-skip"]

    queued_id = queue.enqueue(track_id)
    queue.reserve_next()
    _write_queue_metadata(cfg, queue_id=None, track_id=None)
    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 0}
    assert calls == ["request-skip", "output-skip", "library-skip"]
    assert any(item.id == queued_id for item, _track in QueueRepo(database).list_visible())

    queue.mark_playing(queued_id)
    _write_queue_metadata(cfg, queue_id=queued_id, track_id=track_id, queue_kind="urgent")
    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["request-skip", "output-skip", "library-skip", "play-now-skip"]

    _write_queue_metadata(cfg, queue_id=None, track_id=None)
    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 0}
    assert calls == [
        "request-skip",
        "output-skip",
        "library-skip",
        "play-now-skip",
        "output-skip",
        "library-skip",
    ]


def test_queue_skip_endpoint_liquidsoap_error(
    api_context: tuple[TestClient, Database],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _database = api_context

    class BrokenTelnet:
        def skip_output(self) -> str:
            from manager.playback.telnet import LiquidsoapTelnetError

            raise LiquidsoapTelnetError("down")

        def skip_library_sources(self) -> list[str]:
            return ["unused"]

        def flush_request_queue(self) -> str:
            return "unused"

    routes_module = import_module("manager.api.routes")
    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", BrokenTelnet)

    response = client.post("/queue/skip", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 503


def test_queue_skip_skips_active_request_when_metadata_has_track_without_queue_id(
    api_context: tuple[TestClient, Database],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    track_id = TracksRepo(database).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(database)
    queue.enqueue(track_id)
    queue.reserve_next()
    routes_module = import_module("manager.api.routes")
    _write_queue_metadata(routes_module.get_settings(), queue_id=None, track_id=track_id)
    calls: list[str] = []

    class FakeTelnet:
        def skip_request_queue(self) -> str:
            calls.append("request-skip")
            return "Done"

    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post("/queue/skip", headers={"Authorization": "Bearer secret-token"})

    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["request-skip"]


def test_queue_skip_library_fallback_marks_playing_item_skipped(
    api_context: tuple[TestClient, Database],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    track_id = TracksRepo(database).upsert("youtube0001", "Track", 120)
    queue = QueueRepo(database)
    queue_id = queue.enqueue(track_id)
    queue.mark_playing(queue_id)
    routes_module = import_module("manager.api.routes")
    _write_queue_metadata(routes_module.get_settings(), queue_id=None, track_id=None)
    calls: list[str] = []

    class FakeTelnet:
        def skip_output(self) -> str:
            calls.append("output-skip")
            return "Done"

        def skip_library_sources(self) -> list[str]:
            calls.append("library-skip")
            return ["Done", "Done"]

    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post("/queue/skip", headers={"Authorization": "Bearer secret-token"})

    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["output-skip", "library-skip"]
    assert queue.history(limit=1)[0][0].id == queue_id


def test_track_play_now_pushes_selected_track_as_queue_item(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    old_audio = tmp_path / "old.opus"
    old_audio.write_text("old audio", encoding="utf-8")
    selected_audio = tmp_path / "selected.opus"
    selected_audio.write_text("selected audio", encoding="utf-8")
    tracks = TracksRepo(database)
    old_track_id = tracks.upsert("youtube0001", "Old Track", 120, audio_path=str(old_audio))
    selected_track_id = tracks.upsert(
        "youtube0002",
        "Selected Track",
        120,
        audio_path=str(selected_audio),
    )
    queue = QueueRepo(database)
    pending_id = queue.enqueue(old_track_id, sort_key=90.0)
    queued_id = queue.enqueue(old_track_id, sort_key=100.0)
    queue.reserve_next()
    calls: list[str] = []

    class FakeTelnet:
        def flush_request_queue(self) -> str:
            calls.append("normal-flush")
            return "Done"

        def flush_play_now(self) -> str:
            calls.append("play-now-flush")
            return "Done"

        def push_play_now(self, uri: str) -> str:
            calls.append(f"play-now-push:{uri}")
            return "Queued"

        def skip_output(self) -> str:
            calls.append("output-skip")
            return "Done"

        def skip_library_sources(self) -> list[str]:
            calls.append("library-skip")
            return ["Done", "Done"]

    routes_module = import_module("manager.api.routes")
    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post(
        f"/tracks/{selected_track_id}/play-now",
        headers={"Authorization": "Bearer secret-token"},
    )

    body = response.json()
    normalized = str(selected_audio).replace("\\", "/")
    assert response.status_code == 200
    assert body["status"] == "playing"
    assert body["skipped_queue_items"] == 1
    assert calls == [
        "normal-flush",
        "play-now-flush",
        f'play-now-push:annotate:queue_id="{body["queue_id"]}",track_id="{selected_track_id}",queue_kind="urgent":{normalized}',
    ]
    visible = QueueRepo(database).list_visible()
    assert [item.id for item, _track in visible] == [body["queue_id"], pending_id]
    assert visible[0][0].status == "queued"
    assert visible[0][1].id == selected_track_id
    assert QueueRepo(database).history(limit=1)[0][0].id == queued_id
    assert TracksRepo(database).get(selected_track_id).play_count == 0


def test_track_play_now_replaces_current_request_without_falling_back_to_library(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    old_audio = tmp_path / "old.opus"
    old_audio.write_text("old audio", encoding="utf-8")
    selected_audio = tmp_path / "selected.opus"
    selected_audio.write_text("selected audio", encoding="utf-8")
    tracks = TracksRepo(database)
    old_track_id = tracks.upsert("youtube0001", "Old Track", 120, audio_path=str(old_audio))
    selected_track_id = tracks.upsert(
        "youtube0002",
        "Selected Track",
        120,
        audio_path=str(selected_audio),
    )
    queue = QueueRepo(database)
    playing_id = queue.enqueue(old_track_id, sort_key=100.0)
    queue.mark_playing(playing_id)
    queued_id = queue.enqueue(old_track_id, sort_key=99.0)
    queue.reserve_next()
    calls: list[str] = []
    routes_module = import_module("manager.api.routes")
    cfg = routes_module.get_settings()
    _write_queue_metadata(cfg, queue_id=playing_id, track_id=old_track_id)

    class FakeTelnet:
        def flush_request_queue(self) -> str:
            calls.append("normal-flush")
            return "Done"

        def flush_play_now(self) -> str:
            calls.append("play-now-flush")
            return "Done"

        def push_play_now(self, uri: str) -> str:
            calls.append(f"play-now-push:{uri}")
            return "Queued"

        def skip_output(self) -> str:
            calls.append("output-skip")
            return "Done"

        def skip_library_sources(self) -> list[str]:
            calls.append("library-skip")
            return ["Done", "Done"]

    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post(
        f"/tracks/{selected_track_id}/play-now",
        headers={"Authorization": "Bearer secret-token"},
    )

    body = response.json()
    normalized = str(selected_audio).replace("\\", "/")
    assert response.status_code == 200
    assert body["skipped_queue_items"] == 2
    assert calls == [
        "normal-flush",
        "play-now-flush",
        f'play-now-push:annotate:queue_id="{body["queue_id"]}",track_id="{selected_track_id}",queue_kind="urgent":{normalized}',
    ]
    visible = QueueRepo(database).list_visible()
    assert [item.id for item, _track in visible] == [body["queue_id"]]
    history_ids = {item.id for item, _track in QueueRepo(database).history(limit=10)}
    assert {playing_id, queued_id}.issubset(history_ids)


def test_track_play_now_rejects_unplayable_tracks(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    headers = {"Authorization": "Bearer secret-token"}
    tracks = TracksRepo(database)
    audio = tmp_path / "track.opus"
    audio.write_text("audio", encoding="utf-8")
    no_audio_id = tracks.upsert("youtube0001", "No Audio", 120)
    missing_file_id = tracks.upsert(
        "youtube0002",
        "Missing File",
        120,
        audio_path=str(tmp_path / "missing.opus"),
    )
    inactive_id = tracks.upsert(
        "youtube0003",
        "Inactive",
        120,
        audio_path=str(audio),
        is_active=0,
    )
    deleted_id = tracks.upsert("youtube0004", "Deleted", 120, audio_path=str(audio))
    tracks.ban(deleted_id)

    assert client.post(f"/tracks/{deleted_id}/play-now", headers=headers).status_code == 409
    assert client.post(f"/tracks/{inactive_id}/play-now", headers=headers).status_code == 409
    assert client.post(f"/tracks/{no_audio_id}/play-now", headers=headers).status_code == 409
    assert client.post(f"/tracks/{missing_file_id}/play-now", headers=headers).status_code == 409

    class BrokenTelnet:
        def flush_request_queue(self) -> str:
            return "unused"

        def flush_play_now(self) -> str:
            from manager.playback.telnet import LiquidsoapTelnetError

            raise LiquidsoapTelnetError("down")

        def push_play_now(self, uri: str) -> str:
            return "unused"

        def skip_output(self) -> str:
            return "unused"

        def skip_library_sources(self) -> list[str]:
            return ["unused"]

    routes_module = import_module("manager.api.routes")
    monkeypatch.setattr(routes_module, "LiquidsoapTelnetClient", BrokenTelnet)
    playable_id = tracks.upsert("youtube0005", "Playable", 120, audio_path=str(audio))

    assert client.post(f"/tracks/{playable_id}/play-now", headers=headers).status_code == 503


def test_track_admin_page_and_actions(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    cfg = AppConfig()
    cfg.paths.cache_cold = tmp_path / "cold"
    cfg.paths.cache_hot = tmp_path / "hot"
    cfg.paths.www_html = tmp_path / "www" / "html"
    cfg.paths.cache_cold.mkdir()
    cfg.paths.cache_hot.mkdir()
    _write_web_build(cfg.paths.www_html)
    cfg.secrets.admin_token_raw = SecretStr("secret-token")
    api_module = import_module("manager.api.app")
    _patch_api_settings(monkeypatch, cfg)

    tracks = TracksRepo(database)
    track_id = tracks.upsert("youtube0001", "Track One", 120, channel="Channel")
    failed_id = tracks.upsert("youtube0002", "Broken", 120)
    cold = cfg.paths.cache_cold / "youtube0001.opus"
    hot = cfg.paths.cache_hot / "youtube0001.opus"
    cold.write_text("audio", encoding="utf-8")
    hot.write_text("audio", encoding="utf-8")
    tracks.update_track_audio(track_id=track_id, audio_path=str(cold))
    tracks.increment_fail_count(failed_id)

    admin_html = client.get("/admin").text
    assert "Radio Admin" in admin_html
    assert 'data-radio-app="admin"' in admin_html
    assert "secret-token" not in admin_html
    tracks_response = client.get("/tracks?status=downloaded&q=track").json()
    assert tracks_response["items"][0]["id"] == track_id
    assert tracks_response["stats"]["downloaded"] == 1
    assert client.get("/tracks?status=broken").status_code == 400

    assert client.post(f"/tracks/{track_id}/retry").status_code == 401
    headers = {"Authorization": "Bearer secret-token"}
    retry = client.post(f"/tracks/{track_id}/retry", headers=headers).json()
    assert retry["status"] == "scheduled"
    assert retry["track"]["audio_path"] is None
    assert not cold.exists()
    assert not hot.exists()

    cold.write_text("audio", encoding="utf-8")
    hot.write_text("audio", encoding="utf-8")
    tracks.update_track_audio(track_id=track_id, audio_path=str(cold))
    ban = client.post(f"/tracks/{track_id}/ban", headers=headers).json()
    assert ban["status"] == "banned"
    assert ban["track"]["deleted_at"] is not None
    assert not cold.exists()
    assert not hot.exists()

    restore = client.post(f"/tracks/{track_id}/restore", headers=headers).json()
    assert restore["status"] == "restored"
    assert restore["track"]["deleted_at"] is None
    assert client.post("/tracks/404/restore", headers=headers).status_code == 404

    # Прямо закрываем ветки helper-ов удаления: путь вне cache игнорируется,
    # track без audio_path не добавляет лишний candidate.
    outside = tmp_path / "outside.opus"
    outside.write_text("audio", encoding="utf-8")
    api_module._remove_track_files(
        Track(
            id=999,
            youtube_id="missing-file",
            title="Missing",
            duration_sec=1,
            url="https://youtu.be/missing-file",
        ),
        cfg,
    )
    api_module._remove_track_files(
        Track(
            id=1000,
            youtube_id="outside",
            title="Outside",
            duration_sec=1,
            url="https://youtu.be/outside",
            audio_path=str(outside),
        ),
        cfg,
    )
    assert outside.exists()


def test_admin_token_missing_config(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("RADIO_ADMIN_TOKEN", raising=False)
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    get_settings.cache_clear()

    with pytest.raises(HTTPException) as exception_info:
        require_admin_token("Bearer whatever")

    assert exception_info.value.status_code == 503
    get_settings.cache_clear()
