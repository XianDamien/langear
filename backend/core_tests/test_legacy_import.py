import base64
import copy
import hashlib
from datetime import UTC, date, datetime
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.auth import verify_password
from core.legacy_import import import_snapshot, stable_id
from core.models import Card, Collection, Deck, LegacyImport, MediaReference, Note, User


def legacy_hash(password):
    salt = b"legacy-test-salt"

    def encode(value):
        return base64.urlsafe_b64encode(value).rstrip(b"=").decode()

    return "$".join(
        [
            "pbkdf2_sha256",
            "210000",
            encode(salt),
            encode(hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210000)),
        ]
    )


@pytest.fixture
def snapshot():
    return {
        "revision": "a8f2d4c6e9b1",
        "users": [
            {"id": 1, "username": "user-1", "email": None, "password_hash": None},
            {
                "id": 2,
                "username": "test",
                "email": None,
                "password_hash": legacy_hash("test123"),
            },
        ],
        "decks": [
            {"id": 1, "parent_id": None, "title": "旧课程", "level_index": 0},
            {"id": 2, "parent_id": 1, "title": "第一课", "level_index": 1},
        ],
        "cards": [
            {
                "id": 1,
                "deck_id": 2,
                "card_index": 0,
                "front_text": "Hello world.",
                "back_text": "你好。",
                "audio_path": "legacy/hello.mp3",
                "created_at": "2026-10-14T23:18:00",
            },
            {
                "id": 2,
                "deck_id": 2,
                "card_index": 1,
                "front_text": "Hello again.",
                "back_text": "",
                "audio_path": "legacy/hello.mp3",
            },
        ],
        "user_settings": [
            {
                "user_id": 2,
                "desired_retention": 0.85,
                "learning_steps_json": [5, 15],
                "relearning_steps_json": [10],
                "maximum_interval": 1000,
            }
        ],
        "user_card_fsrs": [
            {
                "user_id": 2,
                "card_id": 1,
                "state": "review",
                "step": None,
                "stability": 2.3,
                "difficulty": 2.1,
                "due": "2026-10-17T03:00:00",
                "last_review": "2026-10-15T12:00:00",
            }
        ],
        "user_card_srs": [],
        "review_log": [
            {
                "id": 1,
                "user_id": 2,
                "card_id": 1,
                "rating": "good",
                "ai_status": "processing",
            }
        ],
        "fsrs_review_log": [{"id": 1, "card_id": 1, "rating": "good"}],
        "settings": [{"key": "my_courses:2:lesson_ids", "value": "[2]"}],
        "user_decks": [],
        "user_deck_cards": [],
        "invitation_codes": [],
    }


def test_import_preserves_content_scope_memory_and_is_idempotent(engine, snapshot):
    with Session(engine) as db, db.begin():
        report = import_snapshot(db, snapshot, "fixture")
        assert (
            report["users"],
            report["decks"],
            report["notes"],
            report["cards"],
            report["media"],
        ) == (2, 6, 6, 15, 1)
        assert report["reviewed_cards"] == 1
    with Session(engine) as db, db.begin():
        col = db.scalar(
            select(Collection).where(
                Collection.owner_user_id == stable_id("fixture", "user", 2)
            )
        )
        assert col.scheduling_config["desired_retention"] == 0.85
        cards = list(db.scalars(select(Card).where(Card.collection_id == col.id)))
        reviewed = [c for c in cards if c.type == "review"]
        assert len(reviewed) == 1
        assert reviewed[0].template_ord == 0
        from core.scheduling import MemoryState, options, study_day
        assert reviewed[0].due_day == study_day(datetime(2026, 10, 16, 12, tzinfo=UTC), col.timezone)
        MemoryState.model_validate(reviewed[0].fsrs_state)
        assert len(options(reviewed[0], datetime(2026, 10, 18, tzinfo=UTC), col, col.scheduling_config)) == 4
        assert reviewed[0].last_reviewed_at.hour == 4
        assert reviewed[0].reps == 1
        assert all(c.fsrs_state is None for c in cards if c.type == "new")
        note = db.get(Note, reviewed[0].note_id)
        note_id = note.id
        assert note.created_at.hour == 15
        note.fields = {**note.fields, "english": "Locally edited"}
        deck = db.get(Deck, reviewed[0].deck_id)
        deck.name = "Renamed"
        ledger = db.get(LegacyImport, "fixture")
        assert ledger.archive["review_log"] == snapshot["review_log"]
        assert ledger.archive["fsrs_review_log"] == snapshot["fsrs_review_log"]
        assert "password_hash" not in ledger.archive["users"][1]
        assert db.scalar(select(func.count()).select_from(MediaReference)) == 6
    with Session(engine) as db, db.begin():
        assert import_snapshot(db, snapshot, "fixture")["already_imported"]
        assert db.scalar(select(func.count()).select_from(Card)) == 15
        assert db.get(Note, note_id).fields["english"] == "Locally edited"


def test_imported_login_upgrades_hash_but_registration_stays_strong(
    engine, snapshot, client
):
    with Session(engine) as db, db.begin():
        import_snapshot(db, snapshot, "fixture")
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "test", "password": "wrong"}
        ).status_code
        == 401
    )
    result = client.post(
        "/api/v1/auth/login", json={"email": " TEST ", "password": "test123"}
    )
    assert result.status_code == 200, result.text
    assert result.json()["user"]["username"] == "test"
    assert result.json()["user"]["email"] is None
    with Session(engine) as db:
        assert db.get(User, stable_id("fixture", "user", 2)).password_hash.startswith(
            "$argon2id$"
        )
        assert db.get(User, stable_id("fixture", "user", 1)).disabled
    assert (
        client.post(
            "/api/v1/auth/register",
            json={"email": "new@example.com", "password": "test123"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": "user-1", "password": "test123"}
        ).status_code
        == 401
    )
    assert not verify_password("pbkdf2_sha256$9999999999$bad$bad", "test123")
    assert not verify_password("pbkdf2_sha256$210000$%$bad", "test123")


def test_conflicts_and_bad_hierarchy_roll_back(engine, snapshot):
    with Session(engine) as db, db.begin():
        db.add(User(email="test", password_hash="existing"))
    with pytest.raises(ValueError, match="conflicting"):
        with Session(engine) as db, db.begin():
            import_snapshot(db, snapshot, "fixture")
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 1
        assert db.scalar(select(func.count()).select_from(Note)) == 0
    broken = copy.deepcopy(snapshot)
    broken["decks"][0]["parent_id"] = 2
    with pytest.raises(ValueError, match="hierarchy"):
        with Session(engine) as db, db.begin():
            import_snapshot(db, broken, "fixture")


def test_changed_snapshot_refused_and_dry_run_is_reversible(engine, snapshot):
    with Session(engine) as db:
        import_snapshot(db, snapshot, "fixture")
        db.rollback()
    with Session(engine) as db, db.begin():
        assert db.scalar(select(func.count()).select_from(User)) == 0
        import_snapshot(db, snapshot, "fixture")
    changed = copy.deepcopy(snapshot)
    changed["cards"][0]["front_text"] = "Changed source"
    with pytest.raises(ValueError, match="snapshot changed"):
        with Session(engine) as db, db.begin():
            import_snapshot(db, changed, "fixture")

def test_repair_is_dry_run_capable_idempotent_and_preserves_new_progress(engine, snapshot):
    from core.legacy_repair import repair
    from core.scheduling import MemoryState
    with Session(engine) as db, db.begin():
        import_snapshot(db, snapshot, "fixture")
        col = db.scalar(select(Collection).where(Collection.owner_user_id == stable_id("fixture", "user", 2)))
        card = db.scalar(select(Card).where(Card.collection_id == col.id, Card.type == "review"))
        card_id = card.id
        card.due_day = date(2026, 10, 16).toordinal()
        card.fsrs_state = {"stability": 2.3, "difficulty": 2.1}
    with Session(engine) as db:
        assert repair(db, "fixture")["memory_cards"] == 1
        db.rollback()
    with Session(engine) as db, db.begin():
        assert db.get(Card, card_id).due_day == date(2026, 10, 16).toordinal()
        assert repair(db, "fixture")["memory_cards"] == 1
    with Session(engine) as db, db.begin():
        card = db.get(Card, card_id)
        MemoryState.model_validate(card.fsrs_state)
        assert card.due_day == (date(2026, 10, 16) - date(1970, 1, 1)).days
        card.fsrs_state = {**card.fsrs_state, "stability": 19}
        card.schedule_revision += 1
        assert repair(db, "fixture")["memory_cards"] == 0
        assert card.fsrs_state["stability"] == 19


def test_imported_legacy_picker_filters_all_generated_directions(engine, snapshot):
    snapshot["settings"].append({"key": "my_courses:2:lesson:2:card_ids", "value": "[2]"})
    with Session(engine) as db, db.begin():
        import_snapshot(db, snapshot, "fixture")
        col = db.scalar(select(Collection).where(Collection.owner_user_id == stable_id("fixture", "user", 2)))
        deck = db.scalar(select(Deck).where(Deck.collection_id == col.id, Deck.deck_guid == "legacy:fixture:deck:2"))
        selected = deck.scheduling_config["study_card_ids"]
        assert len(selected) == 2  # No Chinese prompt on card 2, so no Translation Card.
        note = db.scalar(select(Note).where(Note.collection_id == col.id, Note.guid == "legacy:fixture:card:2"))
        assert set(selected) == {str(c.id) for c in db.scalars(select(Card).where(Card.note_id == note.id))}


def test_cutover_selection_uses_latest_legacy_snapshot_without_overwriting_core_edits(engine, snapshot):
    from core.legacy_repair import repair
    current = {"settings": [
        {"key": "my_courses:2:lesson_ids", "value": [2]},
        {"key": "my_courses:2:lesson:2:card_ids", "value": [2]},
    ]}
    with Session(engine) as db, db.begin():
        import_snapshot(db, snapshot, "fixture")
        assert repair(db, "fixture", current)["selection_decks"] > 0
        assert repair(db, "fixture", current)["selection_decks"] == 0
        col = db.scalar(select(Collection).where(Collection.owner_user_id == stable_id("fixture", "user", 2)))
        deck = db.scalar(select(Deck).where(Deck.collection_id == col.id, Deck.deck_guid == "legacy:fixture:deck:2"))
        assert len(deck.scheduling_config["study_card_ids"]) == 2
        deck.scheduling_config = {**deck.scheduling_config, "study_card_ids": [], "legacy_selection_user_updated": True}
        changed = {"settings": [{"key": "my_courses:2:lesson_ids", "value": []}]}
        repair(db, "fixture", changed)
        assert deck.scheduling_config["study_card_ids"] == []
