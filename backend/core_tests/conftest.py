"""Real PostgreSQL integration tests; never use the dev or production database."""

import os
from pathlib import Path
from uuid import uuid4
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from core.models import Base
from core.seed import seed_system


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("CORE_TEST_DATABASE_URL")
    if not url:
        pytest.skip("CORE_TEST_DATABASE_URL is required for PostgreSQL core tests")
    parsed = make_url(url)
    if (
        not (parsed.database or "").startswith("lan30_test_")
        or parsed.drivername != "postgresql+psycopg"
    ):
        raise RuntimeError(
            "Core tests require a disposable lan30_test_* PostgreSQL database"
        )
    os.environ["CORE_DATABASE_URL"] = url
    os.environ["CORE_CONFIRMATION_SECRET"] = "isolated-core-test-secret-" + str(uuid4())
    os.environ["CORE_AUTH_LIMIT"] = "500"
    os.environ["CORE_COOKIE_SECURE"] = "true"
    from core.config import get_settings
    from core.db import get_engine

    get_settings.cache_clear()
    get_engine.cache_clear()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic-core.ini"))
    command.upgrade(config, "head")
    db_engine = get_engine()
    yield db_engine
    db_engine.dispose()
    get_engine.cache_clear()
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def clean_database(engine):
    # The session fixture has validated a disposable database name before TRUNCATE.
    tables = ", ".join('"' + table + '"' for table in Base.metadata.tables)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE " + tables + " CASCADE"))
    with Session(engine) as db, db.begin():
        seed_system(db)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from core.main import app

    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "http://localhost:3002"}
    ) as value:
        yield value


@pytest.fixture
def account(client):
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "learner@example.com", "password": "a strong test password"},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    client.headers["X-CSRF-Token"] = result["csrf_token"]
    result["deck_id"] = client.get("/api/v1/decks").json()["decks"][0]["id"]
    return result
