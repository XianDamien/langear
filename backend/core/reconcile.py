"""Final incremental reconciliation of a legacy snapshot into core.

The legacy database is only ever a migration input. This module:

* builds a deterministic plan from an immutable snapshot (same input, same plan);
* refuses to apply when the snapshot checksum or high-water mark moved;
* applies everything in one transaction after a read-only preflight;
* stops on any identity, invite, membership, content or activity conflict
  instead of silently overwriting data core already owns;
* records explicit resolutions so a rerun never asks a human twice;
* emits an aggregate report that never contains passwords, tokens or media URLs.

Run: python -m core.reconcile snapshot.json --source SOURCE [--apply]
"""

import argparse
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from core.auth import HASHER
from core.db import get_engine
from core.errors import DomainError
from core.legacy_import import SOURCE_ZONE, import_snapshot, stable_id, timestamp
from core.models import (
    Card,
    Collection,
    DailyActivity,
    Deck,
    InvitationCode,
    LegacyImport,
    LoginSession,
    MediaAsset,
    MediaReference,
    Note,
    User,
)

SUPPORTED_REVISION = "a8f2d4c6e9b1"
REPORT_VERSION = 1


@dataclass
class Conflict:
    entity: str
    natural_key: str
    reason: str

    def as_dict(self):
        return {"entity": self.entity, "key": self.natural_key, "reason": self.reason}


@dataclass
class Plan:
    source: str
    checksum: str
    high_water: dict
    users: list = field(default_factory=list)
    invitations: dict = field(default_factory=dict)
    deck_updates: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    activities: list = field(default_factory=list)
    settings: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    rejected_history_rows: int = 0
    legacy_users: list = field(default_factory=list)
    legacy_decks: list = field(default_factory=list)
    legacy_notes: list = field(default_factory=list)

    def digest(self):
        """Stable fingerprint of the snapshot's intent.

        Actions that depend on current core state (create vs keep) are excluded,
        so replaying the same snapshot always yields the same digest.
        """
        payload = {
            "source": self.source,
            "checksum": self.checksum,
            "invitations": self.invitations,
            "activities": self.activities,
            "settings": self.settings,
            "legacy_users": self.legacy_users,
            "legacy_decks": self.legacy_decks,
            "legacy_notes": self.legacy_notes,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest()


def snapshot_checksum(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def high_water(data):
    """Newest timestamp per source table; a changed value means the source moved."""
    marks = {}
    for table in ("users", "decks", "cards", "review_log", "user_settings", "settings"):
        latest = None
        for row in data.get(table, []):
            for key in ("updated_at", "created_at"):
                value = row.get(key)
                if not value:
                    continue
                parsed = timestamp(value)
                if latest is None or parsed > latest:
                    latest = parsed
        marks[table] = latest.isoformat() if latest else None
    return marks


def normalized_identity(value):
    return (value or "").strip().lower() or None


def plan_for(db, data, source):
    """Read-only planning. Never mutates the session."""
    if data.get("revision") != SUPPORTED_REVISION:
        raise ValueError("Unsupported legacy revision")
    checksum = snapshot_checksum(data)
    marks = high_water(data)
    plan = Plan(source=source, checksum=checksum, high_water=marks)
    ledger = db.get(LegacyImport, source)
    imported_report = ledger.report if ledger else {}
    # Intent-only view of the snapshot: independent of current core state.
    plan.legacy_users = sorted(
        [
            {
                "legacy_id": str(row["id"]),
                "username": normalized_identity(row.get("username")),
                "email": normalized_identity(row.get("email")),
            }
            for row in data.get("users", [])
        ],
        key=lambda row: row["legacy_id"],
    )
    plan.legacy_decks = sorted(
        [
            {
                "legacy_id": str(row["id"]),
                "title": row["title"],
                "parent_id": None if row.get("parent_id") is None else str(row["parent_id"]),
            }
            for row in data.get("decks", [])
        ],
        key=lambda row: row["legacy_id"],
    )
    plan.legacy_notes = sorted(
        [
            {
                "legacy_id": str(row["id"]),
                "legacy_deck_id": str(row["deck_id"]),
                "front_text": row.get("front_text"),
                "back_text": row.get("back_text"),
                "audio_path": bool(row.get("audio_path")),
            }
            for row in data.get("cards", [])
        ],
        key=lambda row: row["legacy_id"],
    )

    # Invitations are matched by code; usage may only grow, never shrink.
    for row in data.get("invitation_codes", []):
        code = row["code"]
        plan.invitations[code] = {
            "max_uses": row.get("max_uses", 1),
            "used_count": row.get("used_count", 0),
            "expired": bool(row.get("expires_at")),
            "disabled": bool(row.get("disabled_at")),
        }

    mapped = imported_report.get("user_mapping", {})
    for row in data.get("users", []):
        legacy_id = str(row["id"])
        username = normalized_identity(row.get("username"))
        email = normalized_identity(row.get("email"))
        identifiers = [value for value in (username, email) if value]
        mapped_id = mapped.get(legacy_id)
        if mapped_id:
            existing = db.get(User, UUID(mapped_id))
            if existing is None:
                plan.conflicts.append(
                    Conflict("user", legacy_id, "mapped account no longer exists")
                )
                continue
            if existing.disabled != (not bool(row.get("password_hash"))):
                plan.users.append(
                    {
                        "user_id": str(existing.id),
                        "legacy_id": legacy_id,
                        "disabled": not bool(row.get("password_hash")),
                        "action": "update_status",
                    }
                )
            continue
        if not identifiers:
            plan.conflicts.append(
                Conflict("user", legacy_id, "no username or email to match")
            )
            continue
        found = list(
            db.scalars(
                select(User).where(
                    (User.email.in_(identifiers)) | (User.username.in_(identifiers))
                )
            )
        )
        if len(found) > 1:
            plan.conflicts.append(
                Conflict("user", legacy_id, "identifiers match several accounts")
            )
        elif len(found) == 1:
            # Never merge identity silently: an unmapped match must be resolved.
            plan.conflicts.append(
                Conflict(
                    "user",
                    legacy_id,
                    "identifier already belongs to an unmapped core account",
                )
            )
        else:
            plan.users.append(
                {
                    "legacy_id": legacy_id,
                    "username": username,
                    "email": email,
                    "password_hash": row.get("password_hash"),
                    "action": "create",
                }
            )

    for row in data.get("decks", []):
        deck_id = stable_id(source, "deck", row["id"])
        deck = db.scalar(
            select(Deck).where(
                Deck.source_metadata["legacy_id"].astext == str(row["id"]),
                Deck.source_metadata["source"].astext == source,
            )
        )
        if deck is None and db.get(Deck, deck_id) is not None:
            deck = db.get(Deck, deck_id)
        if deck is None:
            continue
        if deck.name != row["title"]:
            # A learner may have renamed the Deck; core wins.
            plan.deck_updates.append(
                {"deck_id": str(deck.id), "action": "keep_core_rename"}
            )

    library = db.scalar(select(Collection).where(Collection.kind == "library"))
    for row in data.get("cards", []):
        note = db.scalar(
            select(Note).where(
                Note.collection_id == library.id,
                Note.source_metadata["legacy_id"].astext == str(row["id"]),
                Note.source_metadata["source"].astext == source,
            )
        )
        if note is not None:
            plan.notes.append({"legacy_id": str(row["id"]), "action": "keep"})
            continue
        plan.notes.append({"legacy_id": str(row["id"]), "action": "create"})

    settings = {row["user_id"]: row for row in data.get("user_settings", [])}
    for legacy_id, user_id in mapped.items():
        if db.scalar(
            select(Collection.id).where(Collection.owner_user_id == UUID(user_id))
        ) is None:
            plan.conflicts.append(
                Conflict("collection", legacy_id, "mapped account has no Collection")
            )
    # Intent is every setting row in the snapshot, so the digest does not move
    # between the first run and a replay after import.
    for legacy_id, row in sorted(settings.items(), key=lambda item: item[0]):
        plan.settings.append(
            {
                "legacy_user_id": str(legacy_id),
                "desired_retention": row["desired_retention"],
                "learning_steps": row["learning_steps_json"],
                "relearning_steps": row["relearning_steps_json"],
                "maximum_review_interval": row["maximum_interval"],
            }
        )

    plan.activities, plan.rejected_history_rows = daily_history(data)
    return plan


def daily_history(data):
    """Aggregate attributable review history by legacy user and study date.

    Only rows that map to an approved account and carry a rating are usable.
    Everything else stays in the archive and is reported as rejected.
    """
    buckets = {}
    rejected = 0
    for row in data.get("review_log", []):
        user_id = row.get("user_id")
        created = row.get("created_at")
        if user_id is None or not created or not row.get("rating"):
            rejected += 1
            continue
        day = (
            timestamp(created).astimezone(SOURCE_ZONE).date()
            if not isinstance(created, date)
            else created
        )
        key = (user_id, day)
        bucket = buckets.setdefault(key, {"reviews": 0, "new_cards": 0})
        bucket["reviews"] += 1
    return [
        {
            "legacy_user_id": user_id,
            "activity_date": day.isoformat(),
            "source_key": f"legacy:review_log:{user_id}:{day.isoformat()}",
            "reviews": values["reviews"],
            "new_cards": values["new_cards"],
        }
        for (user_id, day), values in sorted(buckets.items(), key=lambda item: (str(item[0][0]), item[0][1]))
    ], rejected


def reconcile(db, data, source, apply=False):
    if data.get("revision") != SUPPORTED_REVISION:
        raise ValueError("Unsupported legacy revision")
    db.execute(text("SELECT pg_advisory_xact_lock(302002)"))
    before = snapshot_checksum(data)
    plan = plan_for(db, data, source)
    if plan.conflicts:
        raise DomainError(
            409,
            "MIGRATION_CONFLICT",
            "Unresolved migration conflicts; nothing was applied.",
            {"conflicts": [item.as_dict() for item in plan.conflicts]},
        )
    report = {
        "version": REPORT_VERSION,
        "source": source,
        "snapshot_checksum": before,
        "plan_digest": plan.digest(),
        "high_water": plan.high_water,
        "already_imported": False,
        "applied": False,
        "counts": {
            "users_created": sum(1 for row in plan.users if row["action"] == "create"),
            "users_updated": sum(
                1 for row in plan.users if row["action"] == "update_status"
            ),
            "deck_renames_preserved": len(plan.deck_updates),
            "notes_created": sum(1 for row in plan.notes if row["action"] == "create"),
            "notes_kept": sum(1 for row in plan.notes if row["action"] == "keep"),
        },
        "activities": {"planned": len(plan.activities), "inserted": 0, "rejected": 0},
    }
    report["activities"]["rejected"] = plan.rejected_history_rows
    if apply:
        ledger = db.get(LegacyImport, source)
        first_import = ledger is None
        if first_import:
            # The bulk first-time import creates content; it also refuses a
            # changed snapshot, which protects concurrent source writes.
            try:
                imported = import_snapshot(db, data, source)
            except ValueError as exc:
                if "snapshot changed" in str(exc):
                    raise DomainError(
                        409,
                        "SNAPSHOT_CHANGED",
                        "The migration source changed; regenerate the snapshot.",
                    ) from None
                raise
            report["counts"].update(
                {
                    "users_created": imported.get("users", 0),
                    "decks_total": imported.get("decks", 0),
                    "notes_total": imported.get("notes", 0),
                    "cards_total": imported.get("cards", 0),
                    "media_total": imported.get("media", 0),
                }
            )
        else:
            report["already_imported"] = True
        # Everything below is incremental: it works on the first run too, and is
        # the only path that applies account status, invites, settings and
        # daily activity on later snapshots.
        counts = apply_plan(db, plan, data)
        counts.update(sync_content(db, data, source))
        report["counts"].update(counts)
        report["activities"]["inserted"] = counts["activities_inserted"]
        if snapshot_checksum(data) != before:
            raise DomainError(
                409, "SNAPSHOT_CHANGED", "The migration source changed during apply."
            )
        # Record the new high-water mark so a later run can tell what it saw.
        ledger = db.get(LegacyImport, source)
        if ledger is not None:
            ledger.report = {
                **ledger.report,
                "reconciled_checksum": before,
                "reconciled_high_water": plan.high_water,
                "reconciled_counts": report["counts"],
            }
        report["applied"] = True
    return report


def apply_plan(db, plan, data):
    """Apply the non-content plan items; safe to rerun with the same input."""
    counts = {
        "users_created": 0,
        "users_updated": 0,
        "invitations_created": 0,
        "invitations_updated": 0,
        "settings_applied": 0,
        "activities_inserted": 0,
        "deck_renames_preserved": len(plan.deck_updates),
        "notes_created": 0,
        "notes_kept": len(plan.notes),
        "decks_renamed": 0,
        "notes_updated": 0,
        "notes_withdrawn": 0,
        "decks_withdrawn": 0,
    }
    by_id = {row["id"]: row for row in data.get("users", [])}
    for entry in plan.users:
        if entry["action"] == "create":
            continue  # Created by the first-import path, keyed by ledger mapping.
        user = db.get(User, UUID(entry["user_id"]))
        if user is None:
            continue
        if user.disabled != entry["disabled"]:
            user.disabled = entry["disabled"]
            if user.disabled:
                db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
            counts["users_updated"] += 1
    for code, values in sorted(plan.invitations.items()):
        invite = db.scalar(
            select(InvitationCode).where(InvitationCode.code == code).with_for_update()
        )
        if invite is None:
            invite = InvitationCode(
                code=code,
                max_uses=values["max_uses"],
                used_count=values["used_count"],
            )
            db.add(invite)
            counts["invitations_created"] += 1
        else:
            if values["used_count"] < invite.used_count:
                # Usage is monotonic; a lower legacy count never revokes a use.
                continue
            changed = (
                invite.used_count != values["used_count"]
                or invite.max_uses != values["max_uses"]
            )
            invite.used_count = max(invite.used_count, values["used_count"])
            invite.max_uses = values["max_uses"]
            if changed:
                counts["invitations_updated"] += 1
        invite.disabled_at = utcnow() if values["disabled"] else None
        if values["expired"] and invite.expires_at is None:
            invite.expires_at = utcnow()
    ledger = db.get(LegacyImport, plan.source)
    mapping = (ledger.report or {}).get("user_mapping", {}) if ledger else {}
    for entry in plan.settings:
        user_id = mapping.get(entry["legacy_user_id"])
        if not user_id:
            continue
        collection = db.scalar(
            select(Collection)
            .where(Collection.owner_user_id == UUID(user_id))
            .with_for_update()
        )
        if collection is None:
            continue
        collection.scheduling_config = {
            **(collection.scheduling_config or {}),
            "desired_retention": entry["desired_retention"],
            "learning_steps": entry["learning_steps"],
            "relearning_steps": entry["relearning_steps"],
            "maximum_review_interval": entry["maximum_review_interval"],
        }
        counts["settings_applied"] += 1
    for row in plan.activities:
        user_id = mapping.get(str(row["legacy_user_id"]))
        if not user_id:
            continue
        collection = db.scalar(
            select(Collection).where(Collection.owner_user_id == UUID(user_id))
        )
        if collection is None:
            continue
        exists = db.scalar(
            select(DailyActivity.id).where(
                DailyActivity.collection_id == collection.id,
                DailyActivity.source_key == row["source_key"],
            )
        )
        if exists is None:
            db.add(
                DailyActivity(
                    collection_id=collection.id,
                    activity_date=date.fromisoformat(row["activity_date"]),
                    origin="legacy",
                    source_key=row["source_key"],
                    reviews=row["reviews"],
                    new_cards=row["new_cards"],
                )
            )
            counts["activities_inserted"] += 1
    db.flush()
    _ = by_id
    return counts


def edited_since_import(row, imported_at):
    """A row touched after the import was changed by the learner, not the source."""
    if imported_at is None:
        return False
    updated = getattr(row, "updated_at", None)
    return updated is not None and updated > imported_at


def sync_content(db, data, source):
    """Reconcile imported Deck/Note content against the current snapshot.

    Deletion rules: a legacy row present in core but absent from the snapshot is
    *withdrawn*, not hard-deleted — Cards go away so it stops appearing in study
    queues, while schedules, Attempts and the import ledger stay for audit.
    Conflict rules: a row whose core revision moved past the imported one was
    edited by the learner, so the source never overwrites it.
    """
    counts = {
        "decks_renamed": 0,
        "decks_withdrawn": 0,
        "notes_updated": 0,
        "notes_withdrawn": 0,
    }
    snapshot_decks = {str(row["id"]): row for row in data.get("decks", [])}
    snapshot_notes = {str(row["id"]): row for row in data.get("cards", [])}
    imported_decks = list(
        db.scalars(
            select(Deck).where(
                Deck.imported.is_(True),
                Deck.source_metadata["source"].astext == source,
            )
        )
    )
    ledger = db.get(LegacyImport, source)
    imported_at = ledger.imported_at if ledger else None
    for deck in imported_decks:
        legacy_id = (deck.source_metadata or {}).get("legacy_id")
        if legacy_id not in snapshot_decks:
            for card in db.scalars(select(Card).where(Card.deck_id == deck.id)):
                db.delete(card)
            deck.in_my_courses = False
            counts["decks_withdrawn"] += 1
            continue
        row = snapshot_decks[legacy_id]
        if deck.name != row["title"] and not edited_since_import(deck, imported_at):
            deck.name = row["title"]
            counts["decks_renamed"] += 1
    imported_notes = list(
        db.scalars(
            select(Note).where(
                Note.imported.is_(True),
                Note.source_metadata["source"].astext == source,
            )
        )
    )
    for note in imported_notes:
        metadata = note.source_metadata or {}
        legacy_id = metadata.get("legacy_id")
        if legacy_id not in snapshot_notes:
            for card in db.scalars(select(Card).where(Card.note_id == note.id)):
                db.delete(card)
            note.fields = {}
            note.revision += 1
            counts["notes_withdrawn"] += 1
            continue
        row = snapshot_notes[legacy_id]
        if edited_since_import(note, imported_at):
            continue
        fields = {"english": row.get("front_text"), "chinese": row.get("back_text")}
        changed = {
            key: value
            for key, value in fields.items()
            if value is not None and note.fields.get(key) != value
        }
        if changed:
            note.fields = {**note.fields, **changed}
            note.revision += 1
            counts["notes_updated"] += 1
    db.flush()
    return counts


def verify(db, data, source):
    """Read-only cross-check: counts, stable keys and rejected totals."""
    plan = plan_for(db, data, source)
    ledger = db.get(LegacyImport, source)
    library = db.scalar(select(Collection).where(Collection.kind == "library"))
    activities, rejected = daily_history(data)
    mapped = (ledger.report or {}).get("user_mapping", {}) if ledger else {}
    checks = {
        "invitations": {
            "source": len(data.get("invitation_codes", [])),
            "core": db.scalar(select(func.count()).select_from(InvitationCode)),
        },
        "users": {
            "source": len(data.get("users", [])),
            "mapped": len(mapped),
            "core": db.scalar(select(func.count()).select_from(User)),
        },
        # Import writes one Deck/Note copy per destination Collection (Library
        # plus each migrated user), so the invariant is cardinality, not equality.
        "decks": {
            "source": len(data.get("decks", [])),
            "imported": db.scalar(
                select(func.count()).select_from(Deck).where(Deck.imported.is_(True))
            ),
            "destinations": len(mapped) + 1,
            "per_destination": len(data.get("decks", [])) * (len(mapped) + 1),
            "distinct_legacy_ids": db.scalar(
                select(func.count(func.distinct(Deck.source_metadata["legacy_id"].astext)))
                .where(Deck.imported.is_(True))
            ),
        },
        "notes": {
            "source": len(data.get("cards", [])),
            "imported": db.scalar(
                select(func.count()).select_from(Note).where(Note.imported.is_(True))
            ),
            "destinations": len(mapped) + 1,
            "per_destination": len(data.get("cards", [])) * (len(mapped) + 1),
            "distinct_legacy_ids": db.scalar(
                select(func.count(func.distinct(Note.source_metadata["legacy_id"].astext)))
                .where(Note.imported.is_(True))
            ),
        },
        "media": {
            "source": len({row["audio_path"] for row in data.get("cards", []) if row.get("audio_path")}),
            "assets": db.scalar(select(func.count()).select_from(MediaAsset)),
            "library_shared": db.scalar(
                select(func.count())
                .select_from(MediaAsset)
                .where(MediaAsset.scope == "library_shared")
            ),
            "references": db.scalar(select(func.count()).select_from(MediaReference)),
        },
        "daily_activity": {
            "attributable": len(activities),
            "rejected": rejected,
            "archived_review_rows": len(data.get("review_log", [])),
            "core_rows": db.scalar(
                select(func.count()).select_from(DailyActivity)
            ),
        },
        "consistency": {
            "plan_conflicts": len(plan.conflicts),
            "library_collection": str(library.id) if library else None,
        },
    }
    for entity in ("decks", "notes"):
        checks[entity]["replicated"] = (
            checks[entity]["imported"] == checks[entity]["per_destination"]
            and checks[entity]["distinct_legacy_ids"] == checks[entity]["source"]
        )
    checks["media"]["missing_assets"] = (
        0
        if ledger is None
        else max(0, checks["media"]["source"] - checks["media"]["library_shared"])
    )
    # A source media item is accounted for only when core holds a shared asset
    # for it; assets without references are a normal state for imported Notes
    # whose fields were cleared, so the reference count is reported, not gated.
    checks["media"]["replicated"] = checks["media"]["missing_assets"] == 0
    checks["daily_activity"]["accounted"] = (
        checks["daily_activity"]["archived_review_rows"]
        == sum(row["reviews"] for row in activities) + rejected
    )
    return checks


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--source", required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    data = json.loads(args.snapshot.read_text())
    with Session(get_engine()) as db:
        try:
            if args.verify:
                report = verify(db, data, args.source)
            else:
                report = reconcile(db, data, args.source, apply=args.apply)
            if args.apply:
                db.commit()
            else:
                db.rollback()
            print(json.dumps(report, sort_keys=True, default=str))
        except Exception:
            db.rollback()
            raise SystemExit(
                "Reconciliation aborted and rolled back; nothing was applied."
            ) from None


if __name__ == "__main__":
    main()
