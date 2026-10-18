from contextlib import asynccontextmanager
from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from core.release_app import make_release_app


def test_combined_api_keeps_legacy_and_scopes_core_cookies(engine):
    from core.main import app as core
    events = []

    @asynccontextmanager
    async def lifespan(app):
        events.append("start")
        yield
        events.append("stop")

    legacy = Starlette(lifespan=lifespan, routes=[
        Route("/health", lambda request: JSONResponse({"status": "healthy"})),
        Route("/api/v1/auth/me", lambda request: JSONResponse({"legacy": True})),
    ])
    with TestClient(make_release_app(legacy, core), base_url="https://testserver", headers={"Origin": "http://localhost:3002"}) as client:
        assert events == ["start"]
        assert client.get("/health").json() == {"status": "healthy"}
        assert client.get("/api/v1/auth/me").json() == {"legacy": True}
        assert client.get("/api/content/ready").status_code == 200
        response = client.post("/api/content/v1/auth/register", json={"email": "paired@example.com", "password": "a strong paired password"})
        assert response.status_code == 201, response.text
        assert "Path=/api/content/v1" in response.headers["set-cookie"]
        client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
        assert client.get("/api/content/v1/auth/me").status_code == 200
        assert client.post("/api/content/v1/decks", json={"name": "Paired"}).status_code == 201
        assert client.post("/api/content/v1/auth/logout").status_code == 204
        assert client.get("/api/content/v1/auth/me").status_code == 401
    assert events == ["start", "stop"]
