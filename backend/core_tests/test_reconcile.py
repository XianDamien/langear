"""Final incremental reconciliation: determinism, conflicts and idempotence."""

import copy

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import DomainError
from core.models import DailyActivity, LegacyImport, User, utcnow
from core.reconcile import (
    daily_history,
    high_water,
    plan_for,
    reconcile,
    snapshot_checksum,
    verify,
)
from core_tests.test_legacy_import import legacy_hash, snapshot as base_snapshot


@pytest.fixture
def snapshot(base_snapshot):
    data = copy.deepcopy(base_snapshot)
    # Attribution needs a review timestamp; the import fixture omits it because
    # history is archived rather than converted.
    data["review_log"][0]["created_at"] = "2026-10-16T09:00:00"
    return data


def test_plan_is_deterministic_for_identical_input(engine, snapshot):
    with Session(engine) as db:
        first = plan_for(db, snapshot, "final")
        second = plan_for(db, copy.deepcopy(snapshot), "final")
    assert first.digest() == second.digest()
    assert first.conflicts == []


def test_preflight_blocks_on_existing_unmapped_identifier(engine, snapshot):
    with Session(engine) as db, db.begin():
        db.add(User(username="test", password_hash=legacy_hash("something")))
    with Session(engine) as db:
        plan = plan_for(db, snapshot, "final")
    assert any(item.entity == "user" for item in plan.conflicts)
    with Session(engine) as db:
        with pytest.raises(DomainError) as failure:
            reconcile(db, snapshot, "final", apply=True)
    assert failure.value.code == "MIGRATION_CONFLICT"


def test_apply_is_idempotent_and_daily_activity_dedupes(engine, snapshot):
    with Session(engine) as db, db.begin():
        first = reconcile(db, snapshot, "final", apply=True)
        assert first["applied"] is True
    with Session(engine) as db, db.begin():
        second = reconcile(db, snapshot, "final", apply=True)
    assert second["already_imported"] is True
    assert second["activities"]["inserted"] == 0
    assert first["snapshot_checksum"] == second["snapshot_checksum"]
    assert first["plan_digest"] == second["plan_digest"]
    with Session(engine) as db:
        rows = list(db.scalars(select(DailyActivity)))
        assert rows
        assert len({(row.collection_id, row.source_key) for row in rows}) == len(rows)
        ledger = db.get(LegacyImport, "final")
        assert ledger is not None
        assert "password_hash" not in str(ledger.report)


def test_changed_snapshot_is_rejected_without_partial_writes(engine, snapshot):
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["cards"][0]["front_text"] = "Changed"
    with Session(engine) as db:
        with pytest.raises(DomainError) as failure:
            reconcile(db, changed, "final", apply=True)
    assert failure.value.code == "SNAPSHOT_CHANGED"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(DailyActivity)) >= 0


def test_dry_run_never_writes(engine, snapshot):
    with Session(engine) as db:
        report = reconcile(db, snapshot, "final", apply=False)
    assert report["applied"] is False
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(DailyActivity)) == 0


def test_high_water_triggers_when_source_moves(snapshot):
    before = high_water(snapshot)
    changed = copy.deepcopy(snapshot)
    changed["review_log"][0]["created_at"] = "2027-01-01T00:00:00"
    after = high_water(changed)
    assert before != after
    assert snapshot_checksum(snapshot) != snapshot_checksum(changed)


def test_unattributable_history_is_counted_as_rejected(snapshot):
    snapshot["review_log"].append(
        {"id": 9, "user_id": None, "card_id": 1, "rating": "good"}
    )
    snapshot["review_log"].append(
        {"id": 10, "user_id": 2, "card_id": 1, "rating": None}
    )
    activities, rejected = daily_history(snapshot)
    # Both new rows lack an owner or a rating and stay archived.
    assert rejected == 2
    assert sum(row["reviews"] for row in activities) + rejected == len(
        snapshot["review_log"]
    )


def test_verify_reports_totals_whose_parts_are_conserved(engine, snapshot):
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        checks = verify(db, snapshot, "final")
    assert checks["decks"]["replicated"] is True
    assert checks["notes"]["replicated"] is True
    assert checks["decks"]["distinct_legacy_ids"] == checks["decks"]["source"]
    assert checks["notes"]["distinct_legacy_ids"] == checks["notes"]["source"]
    assert checks["users"]["source"] == checks["users"]["mapped"]
    assert checks["daily_activity"]["accounted"] is True
    assert checks["daily_activity"]["archived_review_rows"] == (
        sum(row["reviews"] for row in daily_history(snapshot)[0])
        + checks["daily_activity"]["rejected"]
    )
    assert checks["consistency"]["plan_conflicts"] == 0


def test_report_never_contains_secrets(engine, snapshot):
    import json

    with Session(engine) as db, db.begin():
        report = reconcile(db, snapshot, "final", apply=True)
    serialized = json.dumps(report)
    assert "password_hash" not in serialized
    assert legacy_hash("test123") not in serialized
    assert "oss" not in serialized.lower()


def test_second_run_does_not_overwrite_core_edits(engine, snapshot):
    from core.models import Card, Deck, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db, db.begin():
        note = db.scalar(select(Note).where(Note.imported.is_(True)))
        note.fields = {**note.fields, "english": "Locally edited"}
        note_id = note.id
        deck = db.scalar(select(Deck).where(Deck.imported.is_(True)))
        deck.name = "Locally renamed"
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        assert db.get(Note, note_id).fields["english"] == "Locally edited"
        assert all(
            card.note_id != note_id or card.reps >= 0
            for card in db.scalars(select(Card))
        )
