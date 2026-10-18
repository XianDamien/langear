"""One-shot, transactional legacy staging import. Defaults to a rolled-back dry run.
Same source + same snapshot is a no-op; changed snapshots require explicit reconciliation.
History is archived, not converted to Attempts lacking immutable snapshots.
"""

import argparse
import copy
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import NAMESPACE_URL, uuid5
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from core.content import ContentService
from core.db import get_engine
from core.models import (
    Card,
    Collection,
    Deck,
    DEFAULT_SCHEDULING,
    LegacyImport,
    MediaAsset,
    Note,
    User,
)

from core.scheduling import MemoryState, config_version, study_day

SOURCE_ZONE = ZoneInfo("Asia/Shanghai")


def imported_memory(snapshot, config):
    return MemoryState(
        stability=snapshot["stability"], difficulty=snapshot["difficulty"],
        step=(snapshot.get("step") or 0) if snapshot["state"] != "review" else None,
        desired_retention=config["desired_retention"],
        fsrs_config_version=config_version(config),
    ).model_dump()


def legacy_lesson_ids(data, user_id):
    row = next((r for r in data["settings"] if r["key"] == f"my_courses:{user_id}:lesson_ids"), None)
    value = row["value"] if row else []
    return json.loads(value) if isinstance(value, str) else value


def selection_digest(data, user_id):
    rows = sorted((row["key"], json.loads(row["value"]) if isinstance(row["value"], str) else row["value"])
                  for row in data["settings"] if row["key"].startswith(f"my_courses:{user_id}:"))
    return hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def initialize_selection(db, collection, deck, source, user_id, legacy_deck_id, data):
    selected = legacy_card_ids(data, user_id, legacy_deck_id)
    apply_imported_selection(db, collection, deck, source, selected)
    deck.in_my_courses = legacy_deck_id in legacy_lesson_ids(data, user_id) and selected != []
    deck.scheduling_config = {**deck.scheduling_config, "legacy_selection_initialized": True, "legacy_selection_snapshot": selection_digest(data, user_id)}


def legacy_card_ids(data, user_id, deck_id):
    key = f"my_courses:{user_id}:lesson:{deck_id}:card_ids"
    row = next((r for r in data["settings"] if r["key"] == key), None)
    value = row["value"] if row else None
    return json.loads(value) if isinstance(value, str) else value


def apply_imported_selection(db, collection, deck, source, selected):
    if selected is None:
        deck.scheduling_config = {**deck.scheduling_config, "study_card_ids": None}
        return
    guids = [f"legacy:{source}:card:{value}" for value in selected]
    ids = db.scalars(select(Card.id).join(Note, Card.note_id == Note.id).where(
        Card.collection_id == collection.id, Card.deck_id == deck.id, Note.guid.in_(guids),
    ))
    deck.scheduling_config = {**deck.scheduling_config, "study_card_ids": sorted(str(value) for value in ids)}
    deck.in_my_courses = selected != []



def timestamp(value):
    if not value:
        return None
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        result = result.replace(tzinfo=SOURCE_ZONE)
    return result.astimezone(timezone.utc)


def times(row):
    return {
        key: timestamp(row[key]) for key in ("created_at", "updated_at") if row.get(key)
    }


def stable_id(source, kind, legacy_id):
    return uuid5(NAMESPACE_URL, f"langear-legacy:{source}:{kind}:{legacy_id}")


def import_snapshot(db, data, source):
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,60}", source):
        raise ValueError("Source must be a stable 1–60 character identifier")
    if data.get("revision") != "a8f2d4c6e9b1":
        raise ValueError("Unsupported legacy revision")
    # Lock all imports, then Library, in a fixed order.
    db.execute(text("SELECT pg_advisory_xact_lock(302002)"))
    checksum = hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
    previous = db.get(LegacyImport, source)
    if previous:
        if previous.checksum != checksum:
            raise ValueError(
                "Source snapshot changed; refusing to overwrite imported data"
            )
        return {**previous.report, "already_imported": True}
    # Membership/custom deck schemas need an explicit mapping, never silently flatten.
    if data.get("user_decks") or data.get("user_deck_cards"):
        raise ValueError("Custom legacy deck membership requires a separate mapping")
    library = db.scalar(
        select(Collection).where(Collection.kind == "library").with_for_update()
    )
    if library is None:
        raise ValueError("Run core migrations/seeding before importing")
    deck_rows = {row["id"]: row for row in data["decks"]}
    card_rows = {row["id"]: row for row in data["cards"]}
    if len(deck_rows) != len(data["decks"]) or len(card_rows) != len(data["cards"]):
        raise ValueError("Duplicate legacy IDs")
    ordered_decks, pending = [], dict(deck_rows)
    while pending:
        ready = [
            row
            for row in pending.values()
            if row["parent_id"] is None
            or row["parent_id"] in {x["id"] for x in ordered_decks}
        ]
        if not ready:
            raise ValueError("Missing deck parent or cyclic legacy hierarchy")
        for row in sorted(ready, key=lambda x: (x.get("level_index") or 0, x["id"])):
            ordered_decks.append(row)
            del pending[row["id"]]
    users, collections = {}, {}
    settings = {row["user_id"]: row for row in data["user_settings"]}
    for row in data["users"]:
        username = (row.get("username") or "").strip().lower() or None
        email = (row.get("email") or "").strip().lower() or None
        identifiers = [value for value in (username, email) if value]
        if not identifiers or db.scalar(
            select(User.id).where(
                or_(User.email.in_(identifiers), User.username.in_(identifiers))
            )
        ):
            raise ValueError(
                "Missing or conflicting legacy account identity; no accounts merged"
            )
        user = User(
            id=stable_id(source, "user", row["id"]),
            username=username,
            email=email,
            password_hash=row.get("password_hash") or "",
            disabled=not bool(row.get("password_hash")),
            **times(row),
        )
        db.add(user)
        db.flush()
        config = dict(DEFAULT_SCHEDULING)
        if row["id"] in settings:
            old = settings[row["id"]]
            config.update(
                desired_retention=old["desired_retention"],
                learning_steps=old["learning_steps_json"],
                relearning_steps=old["relearning_steps_json"],
                maximum_review_interval=old["maximum_interval"],
            )
        collection = Collection(
            id=stable_id(source, "collection", row["id"]),
            owner_user_id=user.id,
            timezone="Asia/Shanghai",
            scheduling_config=config,
        )
        db.add(collection)
        db.flush()
        users[row["id"]], collections[row["id"]] = user, collection
    media = {}
    for row in data["cards"]:
        key = row.get("audio_path")
        if row["deck_id"] not in deck_rows or not (row.get("front_text") or "").strip():
            raise ValueError("Card has missing deck or English content")
        if not key:
            continue
        if (
            key.startswith("/")
            or "://" in key
            or ".." in key.split("/")
            or "?" in key
            or len(key) > 600
        ):
            raise ValueError("Unsupported legacy audio key")
        if key in media:
            continue
        asset = db.scalar(select(MediaAsset).where(MediaAsset.object_key == key))
        if asset:
            if (
                asset.scope != "library_shared"
                or asset.kind != "audio"
                or asset.lifecycle != "ready"
            ):
                raise ValueError(
                    "Audio object key conflicts with existing private media"
                )
        else:
            asset = MediaAsset(
                collection_id=library.id,
                collection_kind="library",
                object_key=key,
                kind="audio",
                scope="library_shared",
            )
            db.add(asset)
            db.flush()
        media[key] = asset
    report = {
        "users": len(users),
        "collections": len(collections) + 1,
        "decks": 0,
        "notes": 0,
        "cards": 0,
        "reviewed_cards": 0,
        "media": len(media),
        "archived_review_rows": len(data["review_log"]),
        "archived_unassigned_fsrs_rows": len(data["fsrs_review_log"]),
        "user_mapping": {str(key): str(value.id) for key, value in users.items()},
    }
    snapshots = {
        (row["user_id"], row["card_id"]): row for row in data["user_card_fsrs"]
    }
    # Old global state belonged to legacy user 1 only.
    for row in data["user_card_srs"]:
        existing = snapshots.get((1, row["card_id"]))
        if row.get("last_review") and (
            not existing
            or timestamp(row["last_review"])
            > (
                timestamp(existing.get("last_review"))
                or datetime.min.replace(tzinfo=timezone.utc)
            )
        ):
            snapshots[(1, row["card_id"])] = row
    for legacy_user, collection in [(None, library), *collections.items()]:
        service = ContentService(db, collection)
        nt = service.note_type("sentence")
        decks = {}
        for row in ordered_decks:
            deck = Deck(
                collection_id=collection.id,
                name=row["title"],
                deck_guid=f"legacy:{source}:deck:{row['id']}",
                parent_id=decks[row["parent_id"]].id
                if row["parent_id"] is not None
                else None,
                **times(row),
            )
            db.add(deck)
            db.flush()
            decks[row["id"]] = deck
            report["decks"] += 1
        for row in sorted(
            data["cards"],
            key=lambda x: (x["deck_id"], x.get("card_index") or 0, x["id"]),
        ):
            fields = {"english": row["front_text"], "chinese": row.get("back_text")}
            if row.get("audio_path"):
                fields["reference_audio"] = str(media[row["audio_path"]].id)
            cleaned, references = service.validate_fields(nt.id, fields)
            note = Note(
                collection_id=collection.id,
                guid=f"legacy:{source}:card:{row['id']}",
                note_type_id=nt.id,
                fields=cleaned,
                tags=[],
                **times(row),
            )
            db.add(note)
            db.flush()
            service.sync_media(note, references)
            service.generate(note, decks[row["deck_id"]].id)
            cards = list(db.scalars(select(Card).where(Card.note_id == note.id)))
            report["notes"] += 1
            report["cards"] += len(cards)
            snapshot = snapshots.get((legacy_user, row["id"]))
            if snapshot and snapshot.get("last_review"):
                # Only the original retelling direction inherits its memory.
                card = next((card for card in cards if card.template_ord == 0), None)
                if card is None:
                    raise ValueError("Reviewed legacy card has no retelling template")
                due, last = (
                    timestamp(snapshot["due"]),
                    timestamp(snapshot["last_review"]),
                )
                card.type = snapshot["state"]
                card.queue = "review" if card.type == "review" else "learning"
                card.new_position = None
                if card.type == "review":
                    card.due_day = study_day(due, collection.timezone)
                else:
                    card.due_at = due
                card.last_reviewed_at = last
                card.fsrs_state = imported_memory(snapshot, collection.scheduling_config)
                card.interval_days = max(0, (due - last).total_seconds() / 86400)
                history = [
                    item
                    for item in data["review_log"]
                    if item["user_id"] == legacy_user
                    and item["card_id"] == row["id"]
                    and item.get("rating")
                ]
                card.reps = len(history)
                card.lapses = sum(item["rating"] == "again" for item in history)
                steps = collection.scheduling_config[
                    "relearning_steps"
                    if card.type == "relearning"
                    else "learning_steps"
                ]
                card.learning_steps_remaining = (
                    0
                    if card.type == "review"
                    else max(0, len(steps) - (snapshot.get("step") or 0))
                )
                card.schedule_revision = 1
                report["reviewed_cards"] += 1
            db.flush()
        if legacy_user is not None:
            for legacy_deck_id, deck in decks.items():
                initialize_selection(db, collection, deck, source, legacy_user, legacy_deck_id, data)
    archive = copy.deepcopy(data)
    for row in archive["users"]:
        row["had_password"] = bool(row.pop("password_hash", None))
    # Archive remains maintenance-only: global history cannot be assigned a user safely.
    db.add(
        LegacyImport(source=source, checksum=checksum, report=report, archive=archive)
    )
    db.flush()
    return {**report, "already_imported": False}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text())
    with Session(get_engine()) as db:
        try:
            report = import_snapshot(db, data, args.source)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(json.dumps({**report, "applied": args.apply}))
        except Exception:
            db.rollback()
            # SQLAlchemy exceptions can contain parameters; never print source data/hashes.
            raise SystemExit(
                "Import aborted and rolled back. Inspect schema, identities and source validity in a protected session."
            ) from None


if __name__ == "__main__":
    main()
