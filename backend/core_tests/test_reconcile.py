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


def test_conflicting_core_and_source_settings_abort_reconciliation(engine, snapshot):
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        user = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(select(Collection).where(Collection.owner_user_id == user.id))
        collection.scheduling_config = {
            **collection.scheduling_config,
            "desired_retention": 0.91,
        }
    changed = copy.deepcopy(snapshot)
    changed["user_settings"][0]["desired_retention"] = 0.8
    with Session(engine) as db:
        with pytest.raises(DomainError) as failure:
            reconcile(db, changed, "final", apply=True)
        db.rollback()
    assert failure.value.code == "MIGRATION_CONFLICT"


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
            card.queue == "suspended"
            for card in db.scalars(
                select(Card).where(Card.note_id == by_legacy[str(removed["id"])].id)
            )
        )


def test_withdrawing_imported_note_preserves_study_attempt(engine, snapshot):
    from core.models import Attempt, Card, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        note = db.scalar(
            select(Note).where(
                Note.source_metadata["legacy_id"].astext == "2",
                Note.collection_id != db.scalar(
                    select(Collection.id).where(Collection.kind == "library")
                ),
            )
        )
        card = db.scalar(select(Card).where(Card.note_id == note.id))
        attempt = Attempt(
            collection_id=card.collection_id,
            card_id=card.id,
            note_id=note.id,
            card_template_id=card.card_template_id,
            note_snapshot=dict(note.fields),
            front_snapshot={},
            back_snapshot={},
            answer_snapshot={},
            input_type="none",
            input_snapshot={},
        )
        db.add(attempt)
        db.flush()
        attempt_id, card_id = attempt.id, card.id

    changed = copy.deepcopy(snapshot)
    changed["cards"] = [row for row in changed["cards"] if row["id"] != 2]
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        assert db.get(Attempt, attempt_id) is not None
        assert db.get(Card, card_id).queue == "suspended"


def test_restored_source_note_reactivates_existing_card(engine, snapshot):
    from core.models import Card, MediaReference, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        note = db.scalar(select(Note).where(
            Note.source_metadata["legacy_id"].astext == "2",
            Note.collection_id != db.scalar(select(Collection.id).where(Collection.kind == "library")),
        ))
        note_id = note.id
        card_id = db.scalar(select(Card.id).where(Card.note_id == note_id))
        card_count = db.scalar(select(func.count()).select_from(Card).where(Card.note_id == note_id))

    withdrawn = copy.deepcopy(snapshot)
    withdrawn["cards"] = [row for row in withdrawn["cards"] if row["id"] != 2]
    with Session(engine) as db, db.begin():
        reconcile(db, withdrawn, "final", apply=True)
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        note = db.get(Note, note_id)
        card = db.get(Card, card_id)
        assert note.fields["english"] == "Hello again."
        assert note.fields["reference_audio"]
        assert not note.source_metadata.get("withdrawn")
        assert card.queue != "suspended"
        assert db.scalar(select(func.count()).select_from(MediaReference).where(
            MediaReference.note_id == note_id,
        )) == 1
        assert db.scalar(select(func.count()).select_from(Card).where(Card.note_id == note_id)) == card_count


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


def test_successive_source_deck_changes_keep_converging(engine, snapshot):
    from core.models import Deck

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["decks"][1]["title"] = "First upstream title"
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    changed["decks"][1]["title"] = "Second upstream title"
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        titles = set(
            db.scalars(
                select(Deck.name).where(
                    Deck.source_metadata["legacy_id"].astext == "2"
                )
            )
        )
        assert titles == {"Second upstream title"}


def test_replaying_source_does_not_reset_core_learning_settings(engine, snapshot):
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        user = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(
            select(Collection).where(Collection.owner_user_id == user.id)
        )
        collection.scheduling_config = {
            **collection.scheduling_config,
            "desired_retention": 0.92,
        }
        collection_id = collection.id
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        assert db.get(Collection, collection_id).scheduling_config["desired_retention"] == 0.92


def test_invitation_dates_remain_stable_on_replay(engine, snapshot):
    from datetime import datetime, timezone
    from core.models import InvitationCode

    snapshot["invitation_codes"] = [{
        "code": "FUTURE-1",
        "max_uses": 3,
        "used_count": 1,
        "expires_at": "2030-01-01T00:00:00+00:00",
        "disabled_at": "2026-10-01T00:00:00+00:00",
    }]
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        invite = db.scalar(select(InvitationCode).where(InvitationCode.code == "FUTURE-1"))
        first_disabled_at = invite.disabled_at
        assert invite.expires_at == datetime(2030, 1, 1, tzinfo=timezone.utc)
    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    with Session(engine) as db:
        invite = db.scalar(select(InvitationCode).where(InvitationCode.code == "FUTURE-1"))
        assert invite.disabled_at == first_disabled_at


def test_media_verification_rejects_unrelated_replacement_asset(engine, snapshot):
    from sqlalchemy import delete
    from core.models import MediaAsset, MediaReference

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        source_asset = db.scalar(
            select(MediaAsset).where(MediaAsset.object_key == "legacy/hello.mp3")
        )
        db.execute(
            delete(MediaReference).where(MediaReference.media_asset_id == source_asset.id)
        )
        db.delete(source_asset)
        library = db.scalar(select(Collection).where(Collection.kind == "library"))
        db.add(MediaAsset(
            collection_id=library.id,
            collection_kind="library",
            object_key="unrelated/audio.mp3",
            kind="audio",
            scope="library_shared",
        ))
    with Session(engine) as db:
        assert verify(db, snapshot, "final")["media"]["replicated"] is False


def test_later_snapshot_adds_user_with_collection_and_content(engine, snapshot):
    from core.models import Card, Deck, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["users"].append({
        "id": 3,
        "username": "new-learner",
        "email": None,
        "password_hash": None,
    })
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        learner = db.scalar(select(User).where(User.username == "new-learner"))
        assert learner is not None
        collection = db.scalar(
            select(Collection).where(Collection.owner_user_id == learner.id)
        )
        assert collection is not None
        assert db.scalar(select(func.count()).select_from(Deck).where(Deck.collection_id == collection.id)) == 2
        assert db.scalar(select(func.count()).select_from(Note).where(Note.collection_id == collection.id)) == 2
        assert db.scalar(select(func.count()).select_from(Card).where(Card.collection_id == collection.id)) == 5


def test_later_snapshot_adds_deck_note_cards_and_media(engine, snapshot):
    from core.models import Card, Deck, MediaAsset, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["decks"].append({
        "id": 3, "parent_id": 2, "title": "第二课", "level_index": 2,
    })
    changed["cards"].append({
        "id": 3, "deck_id": 3, "card_index": 0,
        "front_text": "New sentence.", "back_text": "新句子。",
        "audio_path": "legacy/new.mp3",
    })
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        new_decks = list(db.scalars(select(Deck).where(
            Deck.source_metadata["legacy_id"].astext == "3"
        )))
        new_notes = list(db.scalars(select(Note).where(
            Note.source_metadata["legacy_id"].astext == "3"
        )))
        assert len(new_decks) == len(new_notes) == 3
        assert all(db.scalar(select(func.count()).select_from(Card).where(Card.note_id == note.id)) == 3 for note in new_notes)
        assert db.scalar(select(MediaAsset.id).where(MediaAsset.object_key == "legacy/new.mp3")) is not None
        assert verify(db, changed, "final")["media"]["replicated"] is True


def test_later_snapshot_updates_course_membership(engine, snapshot):
    from core.models import Deck

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["settings"][0]["value"] = "[]"
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        learner = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(select(Collection).where(Collection.owner_user_id == learner.id))
        deck = db.scalar(select(Deck).where(
            Deck.collection_id == collection.id,
            Deck.source_metadata["legacy_id"].astext == "2",
        ))
        assert deck.in_my_courses is False


def test_later_snapshot_updates_unmodified_learning_state(engine, snapshot):
    from datetime import datetime, timezone
    from core.models import Card, Note
    from core.scheduling import study_day

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["user_card_fsrs"][0]["due"] = "2026-11-10T03:00:00"
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        learner = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(select(Collection).where(Collection.owner_user_id == learner.id))
        card = db.scalar(select(Card).join(Note, Card.note_id == Note.id).where(
            Card.collection_id == collection.id,
            Card.template_ord == 0,
            Note.source_metadata["legacy_id"].astext == "1",
        ))
        assert card.due_day == study_day(datetime(2026, 11, 9, 19, tzinfo=timezone.utc), collection.timezone)


def test_source_learning_change_cannot_replace_core_attempt(engine, snapshot):
    from core.models import Attempt, Card, Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        learner = db.scalar(select(User).where(User.username == "test"))
        collection = db.scalar(select(Collection).where(Collection.owner_user_id == learner.id))
        card = db.scalar(select(Card).join(Note, Card.note_id == Note.id).where(
            Card.collection_id == collection.id,
            Card.template_ord == 0,
            Note.source_metadata["legacy_id"].astext == "1",
        ))
        db.add(Attempt(
            collection_id=collection.id,
            card_id=card.id,
            note_id=card.note_id,
            card_template_id=card.card_template_id,
            note_snapshot={}, front_snapshot={}, back_snapshot={}, answer_snapshot={},
            input_type="none", input_snapshot={},
        ))
    changed = copy.deepcopy(snapshot)
    changed["user_card_fsrs"][0]["due"] = "2026-11-10T03:00:00"
    with Session(engine) as db:
        with pytest.raises(DomainError) as failure:
            reconcile(db, changed, "final", apply=True)
        db.rollback()
    assert failure.value.code == "MIGRATION_CONFLICT"


def test_replaying_withdrawal_does_not_revise_note_again(engine, snapshot):
    from core.models import Note

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
    changed = copy.deepcopy(snapshot)
    changed["cards"] = [row for row in changed["cards"] if row["id"] != 2]
    with Session(engine) as db, db.begin():
        reconcile(db, changed, "final", apply=True)
        note = db.scalar(select(Note).where(
            Note.source_metadata["legacy_id"].astext == "2"
        ))
        revision = note.revision
    with Session(engine) as db, db.begin():
        replay = reconcile(db, changed, "final", apply=True)
    with Session(engine) as db:
        note = db.scalar(select(Note).where(
            Note.source_metadata["legacy_id"].astext == "2"
        ))
        assert note.revision == revision
        assert replay["counts"]["notes_withdrawn"] == 0


def test_existing_core_invitation_conflict_aborts_without_overwrite(engine, snapshot):
    from core.models import InvitationCode

    with Session(engine) as db, db.begin():
        reconcile(db, snapshot, "final", apply=True)
        db.add(InvitationCode(code="SHARED-1", max_uses=10, used_count=1))
    changed = copy.deepcopy(snapshot)
    changed["invitation_codes"] = [{
        "code": "SHARED-1", "max_uses": 3, "used_count": 2,
        "expires_at": None, "disabled_at": None,
    }]
    with Session(engine) as db:
        with pytest.raises(DomainError) as failure:
            reconcile(db, changed, "final", apply=True)
        db.rollback()
    assert failure.value.code == "MIGRATION_CONFLICT"
    with Session(engine) as db:
        invite = db.scalar(select(InvitationCode).where(InvitationCode.code == "SHARED-1"))
        assert (invite.max_uses, invite.used_count) == (10, 1)
