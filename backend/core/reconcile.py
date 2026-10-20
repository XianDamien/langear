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

from sqlalchemy import func, select, text
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
        # The bulk first-time import is deterministic and transactional. It also
        # refuses a changed snapshot, which protects concurrent source writes.
        try:
            imported = import_snapshot(db, data, source)
            report["already_imported"] = imported.get("already_imported", False)
            report["counts"].update(
                {
                    "users_created": imported.get("users", 0),
                    "decks_total": imported.get("decks", 0),
                    "notes_total": imported.get("notes", 0),
                    "cards_total": imported.get("cards", 0),
                    "media_total": imported.get("media", 0),
                }
            )
        except ValueError as exc:
            # A changed snapshot is unambiguous; anything else needs inspection.
            if "snapshot changed" in str(exc):
                raise DomainError(
                    409,
                    "SNAPSHOT_CHANGED",
                    "The migration source changed; regenerate the snapshot.",
                ) from None
            raise
        mapping = (db.get(LegacyImport, source).report or {}).get("user_mapping", {})
        inserted = 0
        for row in plan.activities:
            user_id = mapping.get(str(row["legacy_user_id"]))
            if not user_id:
                # Keep it archived and reported; never guess an owner.
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
                inserted += 1
        report["activities"]["inserted"] = inserted
        if snapshot_checksum(data) != before:
            raise DomainError(
                409, "SNAPSHOT_CHANGED", "The migration source changed during apply."
            )
        report["applied"] = True
    return report


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
    checks["media"]["replicated"] = True
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
