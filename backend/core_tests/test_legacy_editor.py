"""Original UI content editing: verified identity exchange and scoped incremental content."""

import io
import json
from urllib.error import HTTPError
from uuid import UUID
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from core.config import get_settings
from core.models import LegacyImport, LoginSession


def configure_bridge(monkeypatch, engine, account):
    monkeypatch.setattr(
        get_settings(), "legacy_identity_url", "http://legacy-test/api/v1/auth/me"
    )
    monkeypatch.setattr(get_settings(), "legacy_import_source", "fixture")
    with Session(engine) as db, db.begin():
        db.add(
            LegacyImport(
                source="fixture",
                checksum="0" * 64,
                report={"user_mapping": {"2": account["user"]["id"]}},
                archive={},
            )
        )


def test_exchange_requires_verified_identity_and_trusted_origin(
    client, account, engine, monkeypatch
):
    configure_bridge(monkeypatch, engine, account)
    calls = []

    def upstream(request, timeout):
        calls.append(request)
        assert request.full_url == "http://legacy-test/api/v1/auth/me"
        assert request.get_header("Authorization") == "Bearer valid-legacy-token"
        assert timeout == 5
        return io.BytesIO(json.dumps({"data": {"id": 2, "username": "test"}}).encode())

    monkeypatch.setattr("core.auth.urllib.request.urlopen", upstream)
    client.cookies.clear()
    assert client.post("/api/v1/auth/legacy").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/legacy",
            headers={
                "Origin": "https://evil.test",
                "Authorization": "Bearer valid-legacy-token",
            },
        ).status_code
        == 403
    )
    assert calls == []
    response = client.post(
        "/api/v1/auth/legacy", headers={"Authorization": "Bearer valid-legacy-token"}
    )
    assert response.status_code == 200, response.text
    assert response.json()["user"]["id"] == account["user"]["id"]
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    assert client.post("/api/v1/decks", json={"name": "来自原页面"}).status_code == 201
    assert client.get("/api/v1/auth/me").json()["user"]["id"] == account["user"]["id"]


def test_invalid_or_unmapped_identity_cannot_open_session(
    client, account, engine, monkeypatch
):
    configure_bridge(monkeypatch, engine, account)
    client.cookies.clear()

    def invalid(request, timeout):
        raise HTTPError(request.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr("core.auth.urllib.request.urlopen", invalid)
    assert (
        client.post(
            "/api/v1/auth/legacy", headers={"Authorization": "Bearer forged"}
        ).status_code
        == 401
    )
    monkeypatch.setattr(
        "core.auth.urllib.request.urlopen",
        lambda request, timeout: io.BytesIO(b'{"data":{"id":999}}'),
    )
    assert (
        client.post(
            "/api/v1/auth/legacy", headers={"Authorization": "Bearer other-user"}
        ).status_code
        == 403
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginSession)) == 1


def test_incremental_content_filter_and_collection_isolation(client, account):
    for guid in ["legacy:fixture:1", "user-authored"]:
        response = client.post(
            "/api/v1/notes",
            json={
                "deck_id": account["deck_id"],
                "note_type_key": "vocabulary",
                "guid": guid,
                "fields": {"word": "hello", "meaning": "你好"},
            },
        )
        assert response.status_code == 201
    assert len(client.get("/api/v1/cards").json()["cards"]) == 4
    result = client.get(
        "/api/v1/cards",
        params={"exclude_imported": True, "deck_id": account["deck_id"]},
    )
    assert len(result.json()["cards"]) == 2
    client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "another long password"},
    )
    assert (
        client.get("/api/v1/cards", params={"exclude_imported": True}).json()["cards"]
        == []
    )
    assert (
        client.get(
            "/api/v1/cards",
            params={"exclude_imported": True, "deck_id": account["deck_id"]},
        ).status_code
        == 404
    )
