from __future__ import annotations

from collections.abc import Iterator
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace
from typing import cast

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


@pytest.fixture
def api_context(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, Database]]:
    dsn = f"sqlite+pysqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setenv("RADIO_DATABASE_DSN", dsn)
    monkeypatch.setenv("RADIO_ADMIN_TOKEN", "secret-token")
    get_settings.cache_clear()

    database = Database(app_config=AppConfig(), dsn=dsn)
    Base.metadata.create_all(database.engine)

    app.dependency_overrides[get_database] = lambda: database
    try:
        with TestClient(app) as client:
            yield client, database
    finally:
        app.dependency_overrides.clear()
        database.close()
        get_settings.cache_clear()


def test_health_queue_current_and_admin_enqueue(api_context: tuple[TestClient, Database]) -> None:
    client, database = api_context
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
    assert get_database(cast(Request, request)) is database

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
                "live_offset_sec": 18,
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

    class FakeTelnet:
        def skip_output(self) -> str:
            calls.append("skip")
            return "Done"

        def flush_request_queue(self) -> str:
            calls.append("flush")
            return "Done"

    api_module = import_module("manager.api.app")
    monkeypatch.setattr(api_module, "LiquidsoapTelnetClient", FakeTelnet)

    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["skip"]

    queued_id = queue.enqueue(track_id)
    queue.reserve_next()
    response = client.post("/queue/skip", headers=headers)
    assert response.json() == {"status": "skipped", "queue_items": 1}
    assert calls == ["skip", "flush"]
    assert any(item.id == queued_id for item, _track in QueueRepo(database).history(limit=10))


def test_queue_skip_endpoint_liquidsoap_error(
    api_context: tuple[TestClient, Database],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _database = api_context

    class BrokenTelnet:
        def skip_output(self) -> str:
            from manager.playback.telnet import LiquidsoapTelnetError

            raise LiquidsoapTelnetError("down")

        def flush_request_queue(self) -> str:
            return "unused"

    api_module = import_module("manager.api.app")
    monkeypatch.setattr(api_module, "LiquidsoapTelnetClient", BrokenTelnet)

    response = client.post("/queue/skip", headers={"Authorization": "Bearer secret-token"})
    assert response.status_code == 503


def test_track_admin_page_and_actions(
    api_context: tuple[TestClient, Database],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, database = api_context
    cfg = AppConfig()
    cfg.paths.cache_cold = tmp_path / "cold"
    cfg.paths.cache_hot = tmp_path / "hot"
    cfg.paths.cache_cold.mkdir()
    cfg.paths.cache_hot.mkdir()
    cfg.secrets.admin_token_raw = SecretStr("secret-token")
    api_module = import_module("manager.api.app")
    monkeypatch.setattr(api_module, "get_settings", lambda: cfg)

    tracks = TracksRepo(database)
    track_id = tracks.upsert("youtube0001", "Track One", 120, channel="Channel")
    failed_id = tracks.upsert("youtube0002", "Broken", 120)
    cold = cfg.paths.cache_cold / "youtube0001.opus"
    hot = cfg.paths.cache_hot / "youtube0001.opus"
    cold.write_text("audio", encoding="utf-8")
    hot.write_text("audio", encoding="utf-8")
    tracks.update_track_audio(track_id=track_id, audio_path=str(cold))
    tracks.increment_fail_count(failed_id)

    assert "Radio Admin" in client.get("/admin").text
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
