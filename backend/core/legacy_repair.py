"""Repair only untouched legacy imports; python -m core.legacy_repair --source SOURCE [--apply]."""
import argparse
import json
from datetime import date
from pathlib import Path
from uuid import UUID
from sqlalchemy import select, text
from sqlalchemy.orm import Session
from core.db import get_engine
from core.legacy_import import imported_memory, initialize_selection, selection_digest
from core.models import Card, Collection, Deck, LegacyImport, Note


def repair(db, source, selection_snapshot=None):
    db.execute(text("SELECT pg_advisory_xact_lock(302002)"))
    ledger = db.get(LegacyImport, source)
    if ledger is None:
        raise ValueError("Import source not found")
    report = {"memory_cards": 0, "selection_decks": 0}
    for old_user, user_id in ledger.report["user_mapping"].items():
        collection = db.scalar(select(Collection).where(Collection.owner_user_id == UUID(user_id)).with_for_update())
        if collection is None:
            continue
        cards = db.scalars(select(Card).join(Note, Card.note_id == Note.id).where(
            Card.collection_id == collection.id, Note.guid.startswith(f"legacy:{source}:card:"),
            Card.schedule_revision == 1, Card.last_reviewed_at.is_not(None),
        ).with_for_update(of=Card))
        for card in cards:
            # The broken importer wrote exactly these two fields. Never overwrite newer memory.
            if set(card.fsrs_state or {}) != {"stability", "difficulty"}:
                continue
            step = None if card.type == "review" else max(0, len(collection.scheduling_config[
                "relearning_steps" if card.type == "relearning" else "learning_steps"
            ]) - card.learning_steps_remaining)
            card.fsrs_state = imported_memory({**card.fsrs_state, "state": card.type, "step": step}, collection.scheduling_config)
            if card.due_day is not None and card.due_day >= date(1970, 1, 1).toordinal():
                card.due_day -= date(1970, 1, 1).toordinal()
            card.schedule_revision += 1
            report["memory_cards"] += 1
        for deck in db.scalars(select(Deck).where(
            Deck.collection_id == collection.id, Deck.deck_guid.startswith(f"legacy:{source}:deck:")
        )):
            config = deck.scheduling_config
            if config.get("legacy_selection_user_updated"):
                continue
            if selection_snapshot is None and config.get("legacy_selection_initialized"):
                continue
            if "study_card_ids" in config and "legacy_selection_snapshot" not in config:
                continue
            data = selection_snapshot if selection_snapshot is not None else ledger.archive
            if config.get("legacy_selection_snapshot") == selection_digest(data, old_user):
                continue
            initialize_selection(db, collection, deck, source, old_user, int(deck.deck_guid.rsplit(":", 1)[1]), data)
            report["selection_decks"] += 1
    db.flush()
    return report


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--selection-snapshot", type=Path, help="Explicit cutover snapshot of current legacy my_courses settings")
    args = parser.parse_args()
    with Session(get_engine()) as db:
        result = repair(db, args.source, json.loads(args.selection_snapshot.read_text()) if args.selection_snapshot else None)
        if args.apply:
            db.commit()
        else:
            db.rollback()
        print(json.dumps({**result, "applied": args.apply}))


if __name__ == "__main__":
    main()
