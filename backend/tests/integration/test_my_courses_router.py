"""Legacy course-selection contract, with optional isolated PostgreSQL coverage."""

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Card, Deck, ReviewLog, Setting, User, UserCardFSRS, UserDeck, UserDeckCard
from app.services.auth_service import create_access_token, hash_password

PATH = "/api/v1/my-courses/lessons"


@pytest.fixture(scope="module")
def courses_engine():
    """Never use the runtime database; PostgreSQL gets a disposable schema."""
    url = os.environ.get("MY_COURSES_TEST_DATABASE_URL")
    admin = None
    if url:
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql" or not (parsed.database or "").endswith("_test"):
            raise ValueError("MY_COURSES_TEST_DATABASE_URL must target a PostgreSQL *_test database")
        schema = f"my_courses_test_{uuid4().hex}"
        admin = create_engine(url)
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    else:
        engine = create_engine(
            "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool,
        )
    try:
        Base.metadata.create_all(engine)
        yield engine
    finally:
        engine.dispose()
        if admin:
            with admin.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            admin.dispose()


@pytest.fixture
def courses_sessions(courses_engine):
    with courses_engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(table.delete())
    factory = sessionmaker(bind=courses_engine)
    with factory.begin() as db:
        db.add_all([User(id=1, username="learner-one"), User(id=2, username="learner-two")])
        db.add(Deck(id=101, title="Source", type="source"))
        db.flush()
        db.add(Deck(id=102, title="Unit", type="unit", parent_id=101))
        db.flush()
        db.add_all([
            Deck(id=103, title="Lesson one", type="lesson", parent_id=102),
            Deck(id=104, title="Lesson two", type="lesson", parent_id=102),
        ])
    return factory


def auth(user_id=1):
    return {"Authorization": f"Bearer {create_access_token(user_id)}"}


@pytest.fixture
def courses_client(courses_sessions):
    def override_get_db():
        with courses_sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    # Exercise the registered production app routes without running its runtime
    # schema guard against the application DATABASE_URL.
    client = TestClient(app)
    try:
        yield client
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)


def selection(response, expected):
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["request_id"]
    assert body["data"] == {"lesson_ids": expected}


def test_get_defaults_to_empty_without_writing(courses_client, courses_sessions):
    selection(courses_client.get(PATH, headers=auth()), [])
    with courses_sessions() as db:
        assert db.query(Setting).count() == 0


def test_replace_deduplicate_reload_clear_and_isolate_users(courses_client):
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [104, 103, 104]}), [103, 104])
    selection(courses_client.get(PATH, headers=auth()), [103, 104])
    selection(courses_client.get(PATH, headers=auth(2)), [])
    selection(courses_client.put(PATH, headers=auth(2), json={"lesson_ids": [104]}), [104])
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103]}), [103])
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": []}), [])
    selection(courses_client.get(PATH, headers=auth()), [])
    selection(courses_client.get(PATH, headers=auth(2)), [104])


def test_existing_login_token_can_save_selection(courses_client, courses_sessions):
    with courses_sessions.begin() as db:
        db.get(User, 1).password_hash = hash_password("course-test-password")
    login = courses_client.post(
        "/api/v1/auth/login",
        json={"username": "learner-one", "password": "course-test-password"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['data']['access_token']}"}
    selection(courses_client.put(PATH, headers=headers, json={"lesson_ids": [103]}), [103])
    selection(courses_client.get(PATH, headers=headers), [103])


def test_course_selection_preserves_unrelated_settings(courses_client, courses_sessions):
    with courses_sessions.begin() as db:
        db.add(Setting(key="unrelated-setting", value={"keep": True}))
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103]}), [103])
    with courses_sessions() as db:
        assert db.get(Setting, "unrelated-setting").value == {"keep": True}


@pytest.mark.parametrize("method", ["get", "put"])
@pytest.mark.parametrize("credentials", [None, "invalid", "deleted-user"])
def test_requires_valid_existing_user(courses_client, method, credentials):
    headers = {} if credentials is None else (
        auth(999) if credentials == "deleted-user" else {"Authorization": "Bearer invalid"}
    )
    kwargs = {"json": {"lesson_ids": [103]}} if method == "put" else {}
    assert courses_client.request(method, PATH, headers=headers, **kwargs).status_code == 401


@pytest.mark.parametrize("payload", [
    {}, {"lesson_ids": None}, {"lesson_ids": "103"},
    {"lesson_ids": [-1]}, {"lesson_ids": [0]}, {"lesson_ids": [True]},
    {"lesson_ids": ["103"]}, {"lesson_ids": [103.5]},
    {"lesson_ids": [103], "user_id": 2},
])
def test_rejects_malformed_input_without_changing_selection(courses_client, payload):
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103]}), [103])
    assert courses_client.put(PATH, headers=auth(), json=payload).status_code == 422
    selection(courses_client.get(PATH, headers=auth()), [103])


@pytest.mark.parametrize("invalid_id", [101, 102, 999999, 2**100])
def test_rejects_missing_or_nonlesson_ids_atomically(courses_client, invalid_id):
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103]}), [103])
    response = courses_client.put(PATH, headers=auth(), json={"lesson_ids": [104, invalid_id]})
    assert response.status_code == 400
    assert response.json()["detail"]["error"]["code"] == "INVALID_LESSON_IDS"
    selection(courses_client.get(PATH, headers=auth()), [103])


def test_get_omits_deleted_lessons(courses_client, courses_sessions):
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103, 104]}), [103, 104])
    with courses_sessions.begin() as db:
        db.query(Deck).filter(Deck.id == 104).delete()
    selection(courses_client.get(PATH, headers=auth()), [103])


def test_deselect_preserves_imports_and_learning_history(courses_client, courses_sessions):
    with courses_sessions.begin() as db:
        db.add(Card(id=201, deck_id=103, card_index=0, front_text="Hello"))
        db.add(UserDeck(id=301, user_id=1, origin_deck_id=103, scope_type="lesson", title_snapshot="Lesson one"))
        db.flush()
        db.add(UserDeckCard(user_deck_id=301, card_id=201, new_position=0))
        db.add(UserCardFSRS(user_id=1, card_id=201, state="review", stability=4.5, difficulty=3.2))
        db.add(ReviewLog(id=401, user_id=1, user_deck_id=301, card_id=201, deck_id=103, result_type="single", status="completed", ai_status="completed", rating="good"))
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": [103]}), [103])
    selection(courses_client.put(PATH, headers=auth(), json={"lesson_ids": []}), [])
    with courses_sessions() as db:
        assert db.get(UserDeck, 301) is not None
        assert db.get(UserDeckCard, (301, 201)) is not None
        assert db.get(UserCardFSRS, (1, 201)).stability == 4.5
        assert db.get(ReviewLog, 401).rating == "good"


def test_concurrent_first_writes_persist_one_complete_selection(courses_client, courses_sessions, courses_engine):
    if courses_engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    barrier = Barrier(4)

    # No lifespan in concurrent clients: this test only overrides the request DB.
    def replace(lesson_id):
        barrier.wait(timeout=10)
        client = TestClient(app)
        try:
            return lesson_id, client.put(PATH, headers=auth(), json={"lesson_ids": [lesson_id]})
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(replace, [103, 104, 103, 104]))
    for lesson_id, response in responses:
        selection(response, [lesson_id])
    assert courses_client.get(PATH, headers=auth()).json()["data"]["lesson_ids"] in ([103], [104])
    with courses_sessions() as db:
        assert db.query(Setting).count() == 1


def test_sentence_selection_is_atomic_personal_and_filters_session(courses_client, courses_sessions):
    with courses_sessions.begin() as db:
        db.add_all([Card(id=201, deck_id=103, card_index=0, front_text="Selected"),
                    Card(id=202, deck_id=103, card_index=1, front_text="Not selected"),
                    Card(id=203, deck_id=104, card_index=0, front_text="Other lesson")])
    path = f"{PATH}/103/cards"
    assert courses_client.get(path, headers=auth()).json()["data"]["card_ids"] is None
    result = courses_client.put(path, headers=auth(), json={"card_ids": [201, 201]})
    assert result.status_code == 200, result.text
    assert result.json()["data"] == {"card_ids": [201], "lesson_ids": [103]}
    assert courses_client.get(path, headers=auth()).json()["data"]["card_ids"] == [201]
    assert courses_client.get(path, headers=auth(2)).json()["data"]["card_ids"] is None
    assert courses_client.put(path, headers=auth(), json={"card_ids": [201, 203]}).status_code == 400
    session = courses_client.get("/api/v1/study/session?lesson_id=103", headers=auth())
    assert session.status_code == 200, session.text
    assert [row["id"] for row in session.json()["data"]["cards"]] == [201]
    assert courses_client.put(path, headers=auth(), json={"card_ids": None}).status_code == 200
    session = courses_client.get("/api/v1/study/session?lesson_id=103", headers=auth())
    assert {row["id"] for row in session.json()["data"]["cards"]} == {201, 202}
    assert courses_client.put(path, headers=auth(), json={"card_ids": []}).json()["data"]["lesson_ids"] == []
    assert courses_client.get(path, headers=auth()).json()["data"]["card_ids"] == []
    with courses_sessions() as db:
        assert db.query(Card).count() == 3
        assert db.query(UserDeckCard).count() == 0


@pytest.mark.parametrize("payload", [{}, {"card_ids": [True]}, {"card_ids": ["201"]}, {"card_ids": [-1]}])
def test_sentence_scope_rejects_malformed_input(courses_client, payload):
    assert courses_client.put(f"{PATH}/103/cards", headers=auth(), json=payload).status_code == 422


def test_sentence_scope_requires_authentication(courses_client):
    assert courses_client.get(f"{PATH}/103/cards").status_code == 401
    assert courses_client.put(f"{PATH}/103/cards", json={"card_ids": None}).status_code == 401
