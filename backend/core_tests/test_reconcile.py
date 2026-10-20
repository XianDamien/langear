"""Final incremental reconciliation: determinism, conflicts and idempotence."""

import copy

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from core.errors import DomainError
from core.models import Collection, DailyActivity, LegacyImport, User, utcnow
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


def test_first_import_still_rejects_a_snapshot_that_moved(engine, snapshot):
    """A source that changed before the first import must abort, not half-apply."""
    with Session(engine) as db:
        # Simulate the bulk importer having already seen a different snapshot.
        from core.legacy_import import import_snapshot

        import_snapshot(db, snapshot, "final")
        db.commit()
    changed = copy.deepcopy(snapshot)
    changed["cards"][0]["front_text"] = "Changed"
    with Session(engine) as db:
        # The second call is incremental now, so content changes are accepted;
        # but the first-import path must never silently accept a different
        # snapshot for the same source.
        from core.legacy_import import import_snapshot as bulk

        with pytest.raises(ValueError):
            bulk(db, changed, "final")


def test_reconcile_converges_after_the_first_import(engine, snapshot):
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["review_log"][0]["created_at"] = "2026-10-17T09:00:00"
    with Session(engine) as db, db.begin():
        report = reconcile(db, changed, "final", apply=True)
    assert report["applied"] is True
    with Session(engine) as db:
        # Only the new day is added; the earlier day is not duplicated.
        assert db.scalar(select(func.count()).select_from(DailyActivity)) == 2


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


def test_verify_checks_media_assets_and_references(engine, snapshot):
    from core.models import MediaAsset, MediaReference
    from uuid import UUID

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        checks = verify(db, snapshot, "final")
        assets = list(db.scalars(select(MediaAsset)))
        refs = db.scalar(select(func.count()).select_from(MediaReference))
    assert checks["media"]["source"] == 1
    assert checks["media"]["assets"] == len(assets)
    assert checks["media"]["references"] == refs
    assert checks["media"]["replicated"] is True

    # A missing asset must be reported as a failure, not silently accepted.
    with Session(engine) as db, db.begin():
        from sqlalchemy import delete

        db.execute(delete(MediaReference))
        db.execute(delete(MediaAsset))
    with Session(engine) as db:
        broken = verify(db, snapshot, "final")
    assert broken["media"]["replicated"] is False
    assert broken["media"]["missing_assets"] == 1
    _ = UUID


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


def test_second_run_applies_plan_items_instead_of_only_importing(engine, snapshot):
    """A second, changed snapshot must reconcile users, invites and settings."""
    from core.models import Collection, InvitationCode

    import hashlib as _hashlib

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db, db.begin():
        # The legacy source gained an invite, disabled account 1 and changed a
        # global setting for the account that has a settings row (user 2).
        db.add(InvitationCode(code="BETA-9", max_uses=3, used_count=2))
        user = db.scalar(select(User).where(User.username == "user-1"))
        user.disabled = False
        account_id = user.id
        target = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(
            select(Collection).where(Collection.owner_user_id == target.id)
        )
        collection.scheduling_config = {
            **collection.scheduling_config,
            "desired_retention": 0.91,
        }
        collection_id = collection.id
    with Session(engine) as db, db.begin():
        source = copy.deepcopy(snapshot)
        source["invitation_codes"] = [
            {
                "id": 1,
                "code": "BETA-9",
                "max_uses": 3,
                "used_count": 2,
                "expires_at": None,
                "disabled_at": None,
            }
        ]
        source["users"][0]["password_hash"] = None  # legacy marks it disabled
        source["user_settings"] = [
            {**row, "desired_retention": 0.8} for row in source["user_settings"]
        ]
        # The ledger checksum no longer matches; reconcile must still converge.
        report = reconcile(db, source, "final", apply=True)
    assert report["applied"] is True
    with Session(engine) as db:
        invite = db.scalar(select(InvitationCode).where(InvitationCode.code == "BETA-9"))
        assert invite.used_count == 2
        assert invite.max_uses == 3
        assert db.get(User, account_id).disabled is True
        assert (
            db.get(Collection, collection_id).scheduling_config["desired_retention"]
            == 0.8
        )
    _ = _hashlib


def test_later_snapshot_syncs_content_changes_and_deletions(engine, snapshot):
    """After the first import, Deck/Note changes and removals converge.

    Core-owned edits still win; the source only updates rows the learner has
    not touched. Legacy rows missing from the source become hidden.
    """
    from core.models import Card, Deck, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["decks"][1]["title"] = "第一课（校订）"
    changed["cards"][0]["front_text"] = "Hello revised."
    # The second card is deleted upstream.
    removed = changed["cards"].pop()
    with Session(engine) as db, db.begin():
        report = reconcile(db, changed, "final", apply=True)
    assert report["applied"] is True
    with Session(engine) as db:
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        decks = [
            deck
            for deck in db.scalars(
                select(Deck).where(
                    Deck.collection_id == library.id,
                    Deck.source_metadata["legacy_id"].astext == "2",
                )
            )
        ]
        assert decks and all(deck.name == "第一课（校订）" for deck in decks)
        notes = list(
            db.scalars(select(Note).where(Note.collection_id == library.id))
        )
        by_legacy = {
            (note.source_metadata or {}).get("legacy_id"): note for note in notes
        }
        assert by_legacy["1"].fields["english"] == "Hello revised."
        assert by_legacy[str(removed["id"])].fields == {}
        assert all(
            card.note_id != by_legacy[str(removed["id"])].id
            for card in db.scalars(select(Card))
        )


def test_core_owned_content_edits_are_not_overwritten(engine, snapshot):
    from core.models import Deck, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db, db.begin():
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        note = db.scalar(
            select(Note).where(
                Note.collection_id == library.id,
                Note.source_metadata["legacy_id"].astext == "1",
            )
        )
        note.fields = {**note.fields, "english": "Learner edited"}
        note.revision += 1
        deck = db.scalar(
            select(Deck).where(
                Deck.collection_id == library.id,
                Deck.source_metadata["legacy_id"].astext == "2",
            )
        )
        deck.name = "Learner renamed"
    changed = copy.deepcopy(snapshot)
    changed["decks"][1]["title"] = "Upstream rename"
    changed["cards"][0]["front_text"] = "Upstream text"
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        note = db.scalar(
            select(Note).where(
                Note.collection_id == library.id,
                Note.source_metadata["legacy_id"].astext == "1",
            )
        )
        deck = db.scalar(
            select(Deck).where(
                Deck.collection_id == library.id,
                Deck.source_metadata["legacy_id"].astext == "2",
            )
        )
        assert note.fields["english"] == "Learner edited"
        assert deck.name == "Learner renamed"
