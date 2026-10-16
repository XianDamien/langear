from datetime import timedelta
from uuid import UUID
import pytest
from sqlalchemy import func, inspect, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from core.models import (
    Attempt,
    Card,
    CardTemplate,
    Collection,
    Deck,
    LoginSession,
    MediaAsset,
    MediaReference,
    Note,
    NoteType,
    NoteTypeField,
    User,
    utcnow,
)
from core.seed import seed_system


def test_empty_postgres_migration_seeds_idempotently_and_no_legacy_tables(engine):
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[1] / "alembic-core.ini"))
    command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    command.upgrade(config, "head")
    # Check migration seeds before the ORM seed helper can repair missing rows.
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(NoteType)) == 2
        assert db.scalar(select(func.count()).select_from(NoteTypeField)) == 10
        assert db.scalar(select(func.count()).select_from(CardTemplate)) == 5
        assert db.scalar(select(func.count()).select_from(Collection)) == 1
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from core.models import Base

    with engine.connect() as connection:
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
    inspector = inspect(engine)
    assert not {"study_sessions", "user_decks", "user_card_fsrs", "review_log"} & set(
        inspector.get_table_names()
    )
    with Session(engine) as db, db.begin():
        seed_system(db)
        seed_system(db)
        assert db.scalar(select(func.count()).select_from(NoteType)) == 2
        assert db.scalar(select(func.count()).select_from(NoteTypeField)) == 10
        assert db.scalar(select(func.count()).select_from(CardTemplate)) == 5
        assert db.scalar(select(func.count()).select_from(Collection)) == 1
        assert (
            db.scalar(text("SELECT version_num FROM alembic_version")) == "lan30_0003"
        )
    for table in ["collections", "decks", "notes", "cards", "attempts", "sessions"]:
        assert all(
            c["type"].timezone
            for c in inspector.get_columns(table)
            if c["name"] in {"created_at", "updated_at"}
        )


def test_registration_atomic_unique_email_cookie_flags_and_hashed_tokens(
    client, account, engine
):
    assert UUID(account["user"]["id"]).version == 7
    response = client.post(
        "/api/v1/auth/register",
        json={"email": " LEARNER@example.com ", "password": "a strong test password"},
    )
    assert response.status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert (
            db.scalar(
                select(func.count())
                .select_from(Collection)
                .where(Collection.kind == "user")
            )
            == 1
        )
        assert db.scalar(select(func.count()).select_from(Deck)) == 1
        user = db.scalar(select(User))
        assert user.password_hash.startswith("$argon2id$")
        session = db.scalar(select(LoginSession))
        assert session.token_hash not in client.cookies.values()
        assert session.csrf_hash != account["csrf_token"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "a strong test password"},
    )
    assert login.status_code == 200
    cookie = login.headers["set-cookie"]
    assert (
        "HttpOnly" in cookie
        and "Secure" in cookie
        and "SameSite=lax" in cookie
        and "Path=/api/v1" in cookie
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(LoginSession)) == 1


def test_registration_rollback_when_default_deck_fails(client, engine):
    # Inject a database failure at the last step, not a mocked repository call.
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE decks ADD CONSTRAINT test_reject_default CHECK (name <> 'Default')"
            )
        )
    try:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "rollback@example.com",
                "password": "a strong test password",
            },
        )
        assert response.status_code == 409
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(Collection)
                    .where(Collection.kind == "user")
                )
                == 0
            )
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE decks DROP CONSTRAINT test_reject_default")
            )


def test_csrf_origin_logout_expiry_and_disabled_account(client, account, engine):
    assert client.get("/api/v1/auth/me").status_code == 200
    client.headers.pop("X-CSRF-Token")
    assert client.post("/api/v1/decks", json={"name": "bad"}).status_code == 403
    client.headers["X-CSRF-Token"] = account["csrf_token"]
    assert (
        client.post(
            "/api/v1/decks",
            json={"name": "bad"},
            headers={"Origin": "https://evil.example"},
        ).status_code
        == 403
    )
    refreshed = client.get("/api/v1/auth/csrf").json()
    client.headers["X-CSRF-Token"] = refreshed["csrf_token"]
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    signed_in = client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "a strong test password"},
    )
    assert signed_in.status_code == 200
    with Session(engine) as db, db.begin():
        db.scalar(select(LoginSession)).last_seen_at = utcnow() - timedelta(days=2)
    assert client.get("/api/v1/auth/me").status_code == 401
    client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "a strong test password"},
    )
    with Session(engine) as db, db.begin():
        db.scalar(select(LoginSession)).expires_at = utcnow() - timedelta(seconds=1)
    assert client.get("/api/v1/auth/me").status_code == 401
    with Session(engine) as db, db.begin():
        db.get(User, UUID(account["user"]["id"])).disabled = True
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "learner@example.com", "password": "a strong test password"},
        ).status_code
        == 401
    )


def test_password_change_verifies_old_password_revokes_every_session(
    client, account, engine
):
    bad = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "wrong",
            "new_password": "a different strong password",
        },
    )
    assert bad.status_code == 401
    good = client.post(
        "/api/v1/auth/password",
        json={
            "current_password": "a strong test password",
            "new_password": "a different strong password",
        },
    )
    assert good.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login",
            json={"email": "learner@example.com", "password": "a strong test password"},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/login",
            json={
                "email": "learner@example.com",
                "password": "a different strong password",
            },
        ).status_code
        == 200
    )


def test_rate_limits_count_failed_requests_and_errors_do_not_echo_password(
    client, engine
):
    from core.config import get_settings

    settings = get_settings()
    old = settings.auth_limit
    settings.auth_limit = 2
    try:
        statuses = [
            client.post(
                "/api/v1/auth/login",
                json={
                    "email": "missing@example.com",
                    "password": "a strong test password",
                },
            ).status_code
            for _ in range(3)
        ]
        assert statuses == [401, 401, 429]
    finally:
        settings.auth_limit = old
    response = client.post(
        "/api/v1/auth/register", json={"email": "bad", "password": "secret"}
    )
    assert response.status_code == 422 and "secret" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
    assert client.post("/api/v1/auth/register", content="{").status_code == 400


def setup_two_collections(db):
    users = [User(email=f"u{i}@example.com", password_hash="test") for i in range(2)]
    db.add_all(users)
    db.flush()
    collections = [Collection(owner_user_id=u.id) for u in users]
    db.add_all(collections)
    db.flush()
    decks = [Deck(collection_id=c.id, name="Default") for c in collections]
    nt = db.scalar(select(NoteType).where(NoteType.key == "vocabulary"))
    notes = [
        Note(
            collection_id=c.id,
            note_type_id=nt.id,
            fields={"word": "test", "meaning": "测试"},
        )
        for c in collections
    ]
    db.add_all(decks + notes)
    db.flush()
    template = db.scalar(
        select(CardTemplate).where(CardTemplate.key == "vocabulary_english_to_chinese")
    )
    cards = [
        Card(
            collection_id=c.id,
            note_id=n.id,
            note_type_id=nt.id,
            card_template_id=template.id,
            template_ord=template.ord,
            deck_id=d.id,
            new_position=i + 1,
        )
        for i, (c, n, d) in enumerate(zip(collections, notes, decks))
    ]
    db.add_all(cards)
    db.flush()
    return users, collections, decks, notes, cards


@pytest.mark.parametrize(
    "violation",
    [
        "second_collection",
        "second_library",
        "cross_parent",
        "cross_card_deck",
        "cross_card_note",
        "wrong_template",
        "cross_attempt",
        "unrelated_attempt",
        "cross_private_media",
        "forged_shared_media",
        "contradictory_due",
        "wrong_queue",
        "duplicate_card",
        "filtered_parent",
        "filtered_card_origin",
    ],
)
def test_database_constraints_reject_invalid_ownership_and_state(engine, violation):
    with Session(engine) as db, db.begin():
        users, collections, decks, notes, cards = setup_two_collections(db)
        a, b = collections
        with pytest.raises(IntegrityError), db.begin_nested():
            if violation == "second_collection":
                db.add(Collection(owner_user_id=users[0].id))
            elif violation == "second_library":
                db.add(Collection(kind="library"))
            elif violation == "cross_parent":
                decks[0].parent_id = decks[1].id
            elif violation == "cross_card_deck":
                cards[0].deck_id = decks[1].id
            elif violation == "cross_card_note":
                cards[0].note_id = notes[1].id
            elif violation == "wrong_template":
                template = db.scalar(
                    select(CardTemplate).where(
                        CardTemplate.key == "sentence_translation"
                    )
                )
                cards[0].card_template_id = template.id
            elif violation in {"cross_attempt", "unrelated_attempt"}:
                card = cards[1] if violation == "cross_attempt" else cards[0]
                db.add(
                    Attempt(
                        collection_id=a.id,
                        card_id=card.id,
                        note_id=notes[1].id,
                        card_template_id=card.card_template_id,
                        note_snapshot={},
                        front_snapshot={},
                        back_snapshot={},
                        answer_snapshot={},
                        input_type="none",
                        input_snapshot={},
                    )
                )
            elif violation == "cross_private_media":
                asset = MediaAsset(
                    collection_id=b.id, kind="audio", object_key="private/test.wav"
                )
                db.add(asset)
                db.flush()
                db.add(
                    MediaReference(
                        collection_id=a.id,
                        note_id=notes[0].id,
                        field_key="reference_audio",
                        media_asset_id=asset.id,
                        media_collection_id=b.id,
                        media_scope="private",
                    )
                )
            elif violation == "forged_shared_media":
                db.add(
                    MediaAsset(
                        collection_id=a.id,
                        kind="audio",
                        scope="library_shared",
                        object_key="forged/shared.wav",
                    )
                )
            elif violation == "contradictory_due":
                cards[0].due_day = 5
            elif violation == "wrong_queue":
                cards[0].queue = "review"
            elif violation == "duplicate_card":
                c = cards[0]
                db.add(
                    Card(
                        collection_id=a.id,
                        note_id=c.note_id,
                        note_type_id=c.note_type_id,
                        card_template_id=c.card_template_id,
                        template_ord=c.template_ord,
                        deck_id=c.deck_id,
                        new_position=3,
                    )
                )
            elif violation == "filtered_parent":
                db.add(
                    Deck(
                        collection_id=a.id,
                        name="filtered",
                        kind="filtered",
                        parent_id=decks[0].id,
                    )
                )
            elif violation == "filtered_card_origin":
                cards[0].original_deck_id = decks[0].id
            db.flush()


def test_csrf_refresh_accepts_same_origin_browser_referer(client, account):
    client.headers.pop("Origin")
    assert client.get("/api/v1/auth/csrf").status_code == 403
    assert (
        client.get(
            "/api/v1/auth/csrf", headers={"Referer": "https://evil.example/library"}
        ).status_code
        == 403
    )
    response = client.get(
        "/api/v1/auth/csrf", headers={"Referer": "http://localhost:3002/library"}
    )
    assert response.status_code == 200
    client.headers["X-CSRF-Token"] = response.json()["csrf_token"]
    # Referer is not a substitute for Origin on state-changing requests.
    assert (
        client.post(
            "/api/v1/decks",
            json={"name": "blocked"},
            headers={"Referer": "http://localhost:3002/library"},
        ).status_code
        == 403
    )
