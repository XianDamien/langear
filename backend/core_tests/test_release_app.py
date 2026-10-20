from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.release_app import make_core_app


def test_core_app_keeps_content_path_cookie_and_websocket_scope(engine):
    from core.main import app as core

    with TestClient(
        make_core_app(core),
        base_url="https://testserver",
        headers={"Origin": "http://localhost:3002"},
    ) as client:
        assert client.get("/health").json()["service"] == "collection-core"
        assert client.get("/ready").status_code == 200
        assert client.get("/api/content/ready").status_code == 200
        response = client.post(
            "/api/content/v1/auth/register",
            json={"email": "core-only@example.com", "password": "a strong core only password"},
        )
        assert response.status_code == 201, response.text
        assert "Path=/api/content/v1" in response.headers["set-cookie"]
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert client.get("/api/content/v1/auth/me").status_code == 200
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/api/content/v1/dialogue/sessions/" + str(uuid4()) + "/ws"
            ):
                pass
