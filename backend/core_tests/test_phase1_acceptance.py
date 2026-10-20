"""End-to-end product flow on core alone: register -> course -> review -> settings
-> dashboard -> dialogue, plus the migration rehearsal invariants.
"""

import copy
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from core.models import DailyActivity, Deck, LegacyImport, User
from core.reconcile import reconcile, snapshot_checksum, verify
from core_tests.test_legacy_import import snapshot as base_snapshot
from core_tests.test_review import flip, make_note, next_card, queue, rate


def test_full_product_flow_on_core_only(monkeypatch, client, engine):
    from core.config import get_settings

    identity = client.post(
        "/api/v1/auth/register",
        json={"username": "flow_user", "password": "a long enough password"},
    )
    assert identity.status_code == 201, identity.text
    client.headers["X-CSRF-Token"] = identity.json()["csrf_token"]
    deck_id = client.get("/api/v1/decks").json()["decks"][0]["id"]

    course = client.post("/api/v1/decks", json={"name": "Lesson", "parent_id": deck_id})
    assert course.status_code == 201
    lesson_id = course.json()["id"]
    make_note(
        client,
        {"deck_id": lesson_id},
        {"english": "Hello world.", "chinese": "你好，世界。", "reference_audio": _audio(engine, client)},
        "sentence_retelling",
    )
    assert client.put(
        f"/api/v1/decks/{lesson_id}/membership", json={"joined": True}
    ).json()["in_my_courses"] is True
    assert client.get("/api/v1/my-courses").json()["decks"][0]["id"] == lesson_id

    selection = client.get(f"/api/v1/decks/{lesson_id}/study-selection").json()
    assert selection == {"card_ids": None}
    cards = client.get(
        "/api/v1/cards", params={"deck_id": lesson_id, "study_only": True}
    ).json()["cards"]
    assert len(cards) == 1
    assert client.put(
        f"/api/v1/decks/{lesson_id}/study-selection",
        json={"card_ids": [cards[0]["id"]]},
    ).status_code == 200

    settings = client.put(
        "/api/v1/settings",
        json={"desired_retention": 0.88, "default_deck_scope": [lesson_id]},
    ).json()
    assert settings["default_deck_scope"] == [lesson_id]

    q = queue(client, {"deck_id": lesson_id})
    recording = _audio(engine, client, temporary=True)
    flipped = flip(
        client,
        q,
        next_card(client, q),
        {"type": "audio", "temporary_media_asset_id": recording},
    ).json()
    assert flipped["attempt"]["input_type"] == "audio"
    assert rate(client, q, flipped, "good").status_code == 200

    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["stats"]["todayDone"] == 1
    assert dashboard["stats"]["streakDays"] == 1
    assert dashboard["leaderboard"] == []
    assert client.get("/api/v1/decks/tree").json()["tree"][0]["id"] == deck_id

    # Dialogue consumes exactly this finished round's attempts.
    monkeypatch.setenv("CORE_DIALOGUE_ENABLED", "true")
    get_settings.cache_clear()
    from core import dialogue as module

    def model(kind, context):
        if kind == "scenario":
            # Ground every target expression in the attempt that produced it.
            source = {
                "card_id": context["sources"][0]["card_id"],
                "attempt_id": context["sources"][0]["attempt_id"],
            }
            return {
                "title": "A short greeting",
                "setup_zh": "向朋友问候。",
                "learner_role": "Friend",
                "agent_role": "Classmate",
                "goals": [{"id": "greet", "description_zh": "说一句问候语"}],
                "target_expressions": [
                    {"english": "hello world", "meaning_zh": "你好世界", "source": source},
                    {"english": "world", "meaning_zh": "世界", "source": source},
                ],
            }
        users = [turn["id"] for turn in context["turns"] if turn["role"] == "user"]
        return {
            "summary_zh": "已完成。" if users else "尚未开始。",
            "goals": [
                {"goal_id": "greet", "completed": bool(users), "evidence_turn_ids": users[:1]}
            ],
            "used_expressions": [],
            "practice_points": [],
        }

    monkeypatch.setattr(module, "planner", model)
    session = client.post(
        "/api/v1/dialogue/sessions",
        json={
            "deck_id": lesson_id,
            "review_queue_id": q,
            "entry_key": str(uuid4()),
            "attempt_ids": [flipped["attempt"]["id"]],
        },
    )
    assert session.status_code == 201, session.text
    path = "/api/v1/dialogue/sessions/" + session.json()["id"]
    assert client.post(path + "/finish").status_code == 200
    assert client.post(path + "/review").status_code == 200
    get_settings.cache_clear()


def _audio(engine, client, temporary=False):
    """Insert a MediaAsset owned by the signed-in Collection."""
    from uuid import UUID, uuid4

    from core.models import MediaAsset, utcnow

    collection_id = client.get("/api/v1/collection").json()["id"]
    with Session(engine) as db, db.begin():
        asset = MediaAsset(
            collection_id=UUID(collection_id),
            object_key=f"{uuid4()}.webm",
            kind="audio",
            lifecycle="temporary" if temporary else "ready",
            uploaded_at=utcnow(),
            content_type="audio/webm",
            size_bytes=6,
        )
        db.add(asset)
        db.flush()
        return str(asset.id)


def test_migration_rehearsal_is_repeatable_with_zero_second_writes(engine):
    data = copy.deepcopy(base_snapshot.__wrapped__())
    data["review_log"][0]["created_at"] = "2026-10-16T09:00:00"
    checksum = snapshot_checksum(data)

    with Session(engine) as db, db.begin():
        first = reconcile(db, data, "rehearsal", apply=True)
    with Session(engine) as db:
        after_first = {
            "users": db.scalar(select(func.count()).select_from(User)),
            "activities": db.scalar(select(func.count()).select_from(DailyActivity)),
        }
        first_verify = verify(db, data, "rehearsal")

    # Replaying the identical immutable snapshot must write nothing.
    with Session(engine) as db, db.begin():
        second = reconcile(db, data, "rehearsal", apply=True)
    with Session(engine) as db:
        after_second = {
            "users": db.scalar(select(func.count()).select_from(User)),
            "activities": db.scalar(select(func.count()).select_from(DailyActivity)),
        }
        second_verify = verify(db, data, "rehearsal")

    assert first["applied"] and second["already_imported"]
    assert second["activities"]["inserted"] == 0
    assert after_first == after_second
    assert first["snapshot_checksum"] == second["snapshot_checksum"] == checksum
    assert first["plan_digest"] == second["plan_digest"]
    assert first_verify == second_verify
    assert first_verify["decks"]["replicated"]
    assert first_verify["notes"]["replicated"]
    assert first_verify["daily_activity"]["accounted"]


def test_migration_converges_a_changed_source_after_the_first_import(engine):
    """Later snapshots reconcile instead of aborting, and record what they saw."""
    first = copy.deepcopy(base_snapshot.__wrapped__())
    first["review_log"][0]["created_at"] = "2026-10-16T09:00:00"
    with Session(engine) as db, db.begin():
        reconcile(db, first, "moving", apply=True)
    moved = copy.deepcopy(first)
    moved["decks"][1]["title"] = "Renamed upstream"
    moved["review_log"].append(
        {
            "id": 2,
            "user_id": 2,
            "card_id": 2,
            "rating": "good",
            "created_at": "2026-10-18T09:00:00",
        }
    )
    with Session(engine) as db, db.begin():
        report = reconcile(db, moved, "moving", apply=True)
    assert report["applied"] is True
    assert report["counts"]["decks_renamed"] >= 1
    with Session(engine) as db:
        ledger = db.get(LegacyImport, "moving")
        # The original import ledger stays immutable as an audit record, while
        # the reconciliation snapshot is tracked separately.
        assert ledger.checksum == snapshot_checksum(first)
        assert ledger.report["reconciled_checksum"] == snapshot_checksum(moved)
        assert ledger.report["reconciled_high_water"]["review_log"] is not None
        assert db.scalar(select(func.count()).select_from(Deck).where(Deck.imported.is_(True))) > 0


def test_migration_report_is_free_of_secrets(engine):
    import json

    from core_tests.test_legacy_import import legacy_hash

    data = copy.deepcopy(base_snapshot.__wrapped__())
    data["review_log"][0]["created_at"] = "2026-10-16T09:00:00"
    with Session(engine) as db, db.begin():
        report = reconcile(db, data, "secrets", apply=True)
    serialized = json.dumps(report)
    assert legacy_hash("test123") not in serialized
    assert "password" not in serialized.lower()
    with Session(engine) as db:
        ledger = db.get(LegacyImport, "secrets")
        assert "password_hash" not in json.dumps(ledger.report)


def test_runtime_never_imports_legacy_modules():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    offenders = [
        path
        for path in (backend / "core").rglob("*.py")
        if any(
            line.strip().startswith(("import app", "from app"))
            for line in path.read_text(encoding="utf-8").splitlines()
        )
    ]
    assert offenders == []
    # The legacy package has been deleted; core must not depend on it.
    assert not (backend / "app").exists()
    with Session(__import__("core.db", fromlist=["get_engine"]).get_engine()) as db:
        db.execute(text("SELECT 1"))
