"""Registration invites, identifier login, global settings and Dashboard."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.auth import HASHER
from core.models import (
    Collection,
    DailyActivity,
    Deck,
    InvitationCode,
    Note,
    User,
    utcnow,
)
from core_tests.test_review import flip, make_note, next_card, queue, rate

NEW_USER = {"email": "invited@example.com", "password": "a long enough password"}


def invite(db, code="BETA-1", max_uses=1, **kwargs):
    row = InvitationCode(code=code, max_uses=max_uses, **kwargs)
    db.add(row)
    db.flush()
    return row


def test_invitation_required_registration_consumes_one_use(client, engine):
    from core.config import get_settings

    settings = get_settings()
    settings.invitation_required = True
    try:
        assert client.post("/api/v1/auth/register", json=NEW_USER).json()["error"][
            "code"
        ] == "INVITATION_REQUIRED"
        assert client.post(
            "/api/v1/auth/register", json={**NEW_USER, "invitation_code": "NOPE"}
        ).json()["error"]["code"] == "INVITATION_INVALID"
        with Session(engine) as db, db.begin():
            invite(db, code="BETA-1", max_uses=2)
        response = client.post(
            "/api/v1/auth/register",
            json={**NEW_USER, "invitation_code": "BETA-1"},
        )
        assert response.status_code == 201, response.text
        with Session(engine) as db:
            code = db.scalar(select(InvitationCode).where(InvitationCode.code == "BETA-1"))
            assert code.used_count == 1
            user = db.scalar(select(User).where(User.email == NEW_USER["email"]))
            assert user.invitation_code_id == code.id
        second = client.post(
            "/api/v1/auth/register",
            json={
                "email": "second@example.com",
                "password": "another long password",
                "invitation_code": "BETA-1",
            },
        )
        assert second.status_code == 201
        third = client.post(
            "/api/v1/auth/register",
            json={
                "email": "third@example.com",
                "password": "a third long password",
                "invitation_code": "BETA-1",
            },
        )
        assert third.json()["error"]["code"] == "INVITATION_EXHAUSTED"
    finally:
        settings.invitation_required = False


@pytest.mark.parametrize("bad", ["expired", "disabled"])
def test_unusable_invitation_codes_are_rejected(client, engine, bad):
    from core.config import get_settings

    settings = get_settings()
    settings.invitation_required = True
    try:
        with Session(engine) as db, db.begin():
            past = utcnow() - timedelta(days=1)
            invite(
                db,
                code="BETA-1",
                expires_at=past if bad == "expired" else None,
                disabled_at=past if bad == "disabled" else None,
            )
        response = client.post(
            "/api/v1/auth/register",
            json={**NEW_USER, "invitation_code": "BETA-1"},
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == f"INVITATION_{bad.upper()}"
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(User)) == 0
    finally:
        settings.invitation_required = False


def test_database_rejects_invitation_overuse_and_username_collisions(client, engine):
    with Session(engine) as db, db.begin():
        row = invite(db, code="BETA-1", max_uses=1)
        row.used_count = 1
    with pytest.raises(IntegrityError):
        with Session(engine) as db, db.begin():
            db.execute(
                text("UPDATE invitation_codes SET used_count = used_count + 1")
            )
    with Session(engine) as db, db.begin():
        db.add(
            User(
                username="learner",
                password_hash=HASHER.hash("a long enough password"),
            )
        )
    with pytest.raises(IntegrityError):
        with Session(engine) as db, db.begin():
            db.add(
                User(
                    username="learner",
                    email="other@example.com",
                    password_hash=HASHER.hash("a long enough password"),
                )
            )
    with pytest.raises(IntegrityError):
        with Session(engine) as db, db.begin():
            db.add(
                User(
                    username="Upper",
                    email="upper@example.com",
                    password_hash=HASHER.hash("a long enough password"),
                )
            )


def sign_out(client):
    client.post("/api/v1/auth/csrf")
    client.post("/api/v1/auth/logout")


def test_username_registration_and_identifier_login(client, engine):
    response = client.post(
        "/api/v1/auth/register",
        json={"username": "Polyglot_99", "password": "a long enough password"},
    )
    assert response.status_code == 201, response.text
    assert response.json()["user"]["username"] == "polyglot_99"
    assert response.json()["user"]["email"] is None
    sign_out(client)
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "POLYGLOT_99", "password": "a long enough password"},
    )
    assert login.status_code == 200, login.text
    sign_out(client)
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "invited@example.com", "password": "a long enough password"},
    ).status_code == 401
    conflict = client.post(
        "/api/v1/auth/register",
        json={
            "username": "polyglot_99",
            "email": "new@example.com",
            "password": "a long enough password",
        },
    )
    assert conflict.json()["error"]["code"] == "USERNAME_CONFLICT"
    email_conflict = client.post(
        "/api/v1/auth/register",
        json={"email": "polyglot_99", "password": "a long enough password"},
    )
    assert email_conflict.status_code in (409, 422)


def test_legacy_account_login_upgrades_hash_and_reports_email(client, account, engine):
    with Session(engine) as db, db.begin():
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        other = User(
            email="both@example.com",
            username="both",
            password_hash=HASHER.hash("a long enough password"),
        )
        db.add(other)
        db.flush()
        collection = Collection(owner_user_id=other.id)
        db.add(collection)
        db.flush()
        db.add(Deck(collection_id=collection.id, name="Default"))
        _ = user
    sign_out(client)
    for identifier in ("both@example.com", "both"):
        sign_out(client)
        response = client.post(
            "/api/v1/auth/login",
            json={"email": identifier, "password": "a long enough password"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["user"]["username"] == "both"


def test_disabled_account_cannot_use_existing_session_or_sign_in(client, account, engine, monkeypatch):
    from core import auth as auth_module

    with Session(engine) as db, db.begin():
        user = db.get(User, __import__("uuid").UUID(account["user"]["id"]))
        user.disabled = True
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "a strong test password"},
    ).status_code == 401


def test_account_can_disable_itself_through_the_api(client, account, engine):
    """Deactivation is self-service; no learner can disable another account."""
    path = "/api/v1/auth/disable"
    # Wrong password must not deactivate the account.
    refused = client.post(path, json={"password": "not the password"})
    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "INVALID_CREDENTIALS"
    assert client.get("/api/v1/auth/me").status_code == 200
    response = client.post(path, json={"password": "a strong test password"})
    assert response.status_code == 200, response.text
    assert response.json() == {"disabled": True}
    # The live session is revoked and sign-in is refused afterwards.
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        json={"email": "learner@example.com", "password": "a strong test password"},
    ).status_code == 401
    with Session(engine) as db:
        assert db.get(User, __import__("uuid").UUID(account["user"]["id"])).disabled is True


def test_operator_can_disable_an_account_without_an_admin_role(client, account, engine):
    """Operators disable accounts through the CLI, not through a product route."""
    from uuid import UUID

    from core.auth import disable_user

    with Session(engine) as db, db.begin():
        result = disable_user(db, UUID(account["user"]["id"]))
    assert result == {"user_id": account["user"]["id"], "disabled": True}
    assert client.get("/api/v1/auth/me").status_code == 401


def test_settings_defaults_partial_update_inheritance_and_scope(client, account, engine):
    response = client.get("/api/v1/settings")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["desired_retention"] == 0.9
    assert data["learning_steps"] == [15]
    assert data["maximum_review_interval"] == 36500
    assert data["default_deck_scope"] == []
    update = client.put(
        "/api/v1/settings",
        json={
            "desired_retention": 0.85,
            "learning_steps": [5, 20],
            "relearning_steps": [10],
            "maximum_review_interval": 900,
            "default_deck_scope": [account["deck_id"]],
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["desired_retention"] == 0.85
    assert update.json()["learning_steps"] == [5, 20]
    assert update.json()["default_deck_scope"] == [account["deck_id"]]
    # Omitted fields are unchanged, not reset.
    partial = client.put("/api/v1/settings", json={"desired_retention": 0.8})
    assert partial.json()["learning_steps"] == [5, 20]
    assert partial.json()["desired_retention"] == 0.8
    deck = client.put(
        "/api/v1/decks/" + account["deck_id"] + "/settings",
        json={
            "daily_new_limit": 3,
            "daily_review_limit": 4,
            "desired_retention": 0.75,
            "maximum_interval": 900,
            "learning_steps": [5, 20],
            "relearning_steps": [10],
        },
    )
    assert deck.status_code == 200, deck.text
    assert deck.json()["daily_new_limit"] == 3
    # Collection-only values cannot be shadowed per Deck.
    assert client.put(
        "/api/v1/decks/" + account["deck_id"] + "/settings",
        json={
            "daily_new_limit": 3,
            "daily_review_limit": 4,
            "desired_retention": 0.75,
            "maximum_interval": 1000,
            "learning_steps": [5, 20],
            "relearning_steps": [10],
        },
    ).json()["error"]["code"] == "COLLECTION_SETTING_ONLY"


def test_settings_reject_foreign_and_duplicate_scope_decks(client, account, engine):
    with Session(engine) as db, db.begin():
        other = User(
            email="scope-other@example.com", password_hash=HASHER.hash("x" * 16)
        )
        db.add(other)
        db.flush()
        collection = Collection(owner_user_id=other.id)
        db.add(collection)
        db.flush()
        foreign = Deck(collection_id=collection.id, name="Foreign")
        db.add(foreign)
        db.flush()
        foreign_id = str(foreign.id)
    response = client.put("/api/v1/settings", json={"default_deck_scope": [foreign_id]})
    assert response.json()["error"]["code"] == "DECK_SCOPE_INVALID"
    duplicate = client.put(
        "/api/v1/settings",
        json={"default_deck_scope": [account["deck_id"], account["deck_id"]]},
    )
    assert duplicate.status_code == 422
    invalid = client.put("/api/v1/settings", json={"desired_retention": 0.5})
    assert invalid.status_code == 422


def test_dashboard_counts_attempts_streak_and_imported_history(client, account, engine):
    empty = client.get("/api/v1/dashboard").json()
    assert empty["stats"]["dailyDone"] == 0
    assert empty["stats"]["streakDays"] == 0
    assert empty["stats"]["reviewsPending"] == 0
    assert len(empty["heatmap"]) == 90
    assert len(empty["weeklyTrend"]) == 7
    assert empty["leaderboard"] == []
    make_note(client, account)
    q = queue(client, account)
    flipped = flip(client, q, next_card(client, q)).json()
    assert rate(client, q, flipped, "good").status_code == 200
    data = client.get("/api/v1/dashboard").json()
    assert data["stats"]["todayDone"] == 1
    assert data["stats"]["todayNew"] == 1
    assert data["stats"]["todayReview"] == 0
    assert data["stats"]["streakDays"] == 1
    assert data["heatmap"][-1]["count"] == 1
    assert data["weeklyTrend"][-1]["sentences"] == 1


def test_dashboard_counts_imported_cards_as_pending_reviews(client, account, engine):
    """Migrated content is real study work and must appear in the queue counts."""
    card = make_note(client, account)["cards"][0]
    assert client.get("/api/v1/dashboard").json()["stats"]["reviewsPending"] == 1
    with Session(engine) as db, db.begin():
        deck = db.get(Deck, UUID(account["deck_id"]))
        deck.imported = True
        deck.source_metadata = {"kind": "deck", "source": "fixture", "legacy_id": "42"}
        note = db.get(Note, UUID(card["note_id"]))
        note.imported = True
        note.source_metadata = {"kind": "card", "source": "fixture", "legacy_id": "101"}
    assert client.get("/api/v1/dashboard").json()["stats"]["reviewsPending"] == 1


def test_dashboard_merges_imported_days_without_double_counting(client, account, engine):
    from uuid import UUID
    from core.dashboard import day_date
    from core.scheduling import study_day

    collection_id = UUID(account["collection"]["id"])
    today = study_day(utcnow(), "Asia/Shanghai")
    with Session(engine) as db, db.begin():
        db.add_all(
            [
                DailyActivity(
                    collection_id=collection_id,
                    activity_date=day_date(today - 1),
                    origin="legacy",
                    source_key="legacy:day:old",
                    reviews=4,
                    new_cards=3,
                ),
                # A live-attempt day wins over imported history for the same day.
                DailyActivity(
                    collection_id=collection_id,
                    activity_date=day_date(today),
                    origin="legacy",
                    source_key="legacy:day:today",
                    reviews=99,
                    new_cards=99,
                ),
            ]
        )
    make_note(client, account)
    q = queue(client, account)
    flipped = flip(client, q, next_card(client, q)).json()
    rate(client, q, flipped, "good")
    data = client.get("/api/v1/dashboard").json()
    assert data["stats"]["todayDone"] == 1
    assert data["stats"]["streakDays"] == 2
    imported_days = {row["date"]: row["count"] for row in data["heatmap"]}
    assert imported_days[day_date(today - 1).isoformat()] == 4


def test_dashboard_streak_breaks_on_gap_and_handles_timezone_rollover(client, account, engine):
    from uuid import UUID
    from core.dashboard import day_date
    from core.scheduling import study_day

    collection_id = UUID(account["collection"]["id"])
    today = study_day(utcnow(), "Asia/Shanghai")
    with Session(engine) as db, db.begin():
        db.add(
            DailyActivity(
                collection_id=collection_id,
                activity_date=day_date(today - 3),
                source_key="legacy:gap",
                reviews=1,
            )
        )
    assert client.get("/api/v1/dashboard").json()["stats"]["streakDays"] == 0
    with Session(engine) as db, db.begin():
        db.add_all(
            [
                DailyActivity(
                    collection_id=collection_id,
                    activity_date=day_date(today - 1),
                    source_key="legacy:yesterday",
                    reviews=2,
                ),
                DailyActivity(
                    collection_id=collection_id,
                    activity_date=day_date(today - 2),
                    source_key="legacy:gap2",
                    reviews=2,
                ),
                DailyActivity(
                    collection_id=collection_id,
                    activity_date=day_date(today),
                    source_key="legacy:today",
                    reviews=2,
                ),
            ]
        )
    # Today, yesterday, the day before and the original day-3 row form one
    # contiguous run of four; the earlier gap assertion proves gaps do break it.
    assert client.get("/api/v1/dashboard").json()["stats"]["streakDays"] == 4


def test_dashboard_is_collection_isolated(client, account):
    from fastapi.testclient import TestClient
    from core.main import app

    make_note(client, account)
    q = queue(client, account)
    flipped = flip(client, q, next_card(client, q)).json()
    rate(client, q, flipped, "good")
    with TestClient(
        app, base_url="https://testserver", headers={"Origin": "http://localhost:3002"}
    ) as other:
        identity = other.post(
            "/api/v1/auth/register",
            json={"email": "dash@example.com", "password": "another strong password"},
        ).json()
        other.headers["X-CSRF-Token"] = identity["csrf_token"]
        data = other.get("/api/v1/dashboard").json()
        assert data["stats"]["todayDone"] == 0
        assert data["stats"]["streakDays"] == 0
        assert other.get("/api/v1/settings").json()["default_deck_scope"] == []
