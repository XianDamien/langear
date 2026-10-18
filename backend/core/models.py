"""PostgreSQL content baseline; all ownership edges are composite foreign keys."""

from datetime import datetime, timezone
from uuid import UUID
from uuid6 import uuid7
from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Entity:
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid7)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class User(Entity, Base):
    __tablename__ = "users"
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    username: Mapped[str | None] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        CheckConstraint("email = lower(trim(email))", name="ck_user_email_normalized"),
    )


DEFAULT_SCHEDULING = {
    "learning_steps": [15],
    "relearning_steps": [15],
    "desired_retention": 0.9,
    "maximum_review_interval": 36500,
    "sibling_burying": True,
    "study_day_rollover_hour": 4,
    "new_limit": 20,
    "review_limit": 200,
    "new_card_gather_order": "random_cards",
    "new_card_sort_order": "order_gathered",
    "new_review_order": "after_reviews",
    "interday_learning_review_order": "before_reviews",
    "review_sort_order": "retrievability_descending",
}


class Collection(Entity, Base):
    __tablename__ = "collections"
    owner_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True
    )
    kind: Mapped[str] = mapped_column(String(16), default="user")
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Shanghai")
    schema_version: Mapped[int] = mapped_column(Integer, default=1)
    next_new_position: Mapped[int] = mapped_column(BigInteger, default=0)
    scheduling_config: Mapped[dict] = mapped_column(
        JSONB, default=lambda: dict(DEFAULT_SCHEDULING)
    )
    __table_args__ = (
        CheckConstraint(
            "(kind = 'user' AND owner_user_id IS NOT NULL) OR (kind = 'library' AND owner_user_id IS NULL)",
            name="ck_collection_owner",
        ),
        UniqueConstraint("id", "kind"),
        CheckConstraint("next_new_position >= 0", name="ck_collection_position"),
        Index(
            "uq_single_library",
            "kind",
            unique=True,
            postgresql_where=text("kind = 'library'"),
        ),
    )


class LoginSession(Entity, Base):
    __tablename__ = "sessions"
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )


class AuthRateLimit(Base):
    __tablename__ = "auth_rate_limits"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    count: Mapped[int] = mapped_column(Integer)


class NoteType(Entity, Base):
    __tablename__ = "note_types"
    key: Mapped[str] = mapped_column(String(32), unique=True)
    display_name: Mapped[str] = mapped_column(String(80))


class NoteTypeField(Entity, Base):
    __tablename__ = "note_type_fields"
    note_type_id: Mapped[UUID] = mapped_column(ForeignKey("note_types.id"))
    key: Mapped[str] = mapped_column(String(32))
    ord: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(16))
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (
        UniqueConstraint("note_type_id", "key"),
        UniqueConstraint("note_type_id", "ord"),
        CheckConstraint("kind IN ('text','audio','image')", name="ck_field_kind"),
    )


class CardTemplate(Entity, Base):
    __tablename__ = "card_templates"
    note_type_id: Mapped[UUID] = mapped_column(ForeignKey("note_types.id"))
    key: Mapped[str] = mapped_column(String(80), unique=True)
    ord: Mapped[int] = mapped_column(Integer)
    required_fields: Mapped[list] = mapped_column(JSONB)
    q_format: Mapped[list] = mapped_column(JSONB)
    a_format: Mapped[list] = mapped_column(JSONB)
    answer_field: Mapped[str] = mapped_column(String(32))
    input_type: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("note_type_id", "ord"),
        UniqueConstraint("note_type_id", "id", "ord"),
        CheckConstraint(
            "input_type IN ('none','audio','text')", name="ck_template_input"
        ),
    )


class Scoped:
    collection_id: Mapped[UUID] = mapped_column(
        ForeignKey("collections.id", ondelete="CASCADE"), index=True
    )


class Deck(Entity, Scoped, Base):
    __tablename__ = "decks"
    in_my_courses: Mapped[bool] = mapped_column(Boolean, default=False, server_default=text("false"))
    name: Mapped[str] = mapped_column(String(200))
    deck_guid: Mapped[str] = mapped_column(String(100), default=lambda: str(uuid7()))
    kind: Mapped[str] = mapped_column(String(16), default="standard")
    parent_id: Mapped[UUID | None] = mapped_column(Uuid)
    parent_kind: Mapped[str] = mapped_column(String(16), default="standard")
    scheduling_config: Mapped[dict] = mapped_column(JSONB, default=dict)
    filter_config: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "id", "kind"),
        UniqueConstraint("collection_id", "deck_guid"),
        ForeignKeyConstraint(
            ["collection_id", "parent_id", "parent_kind"],
            ["decks.collection_id", "decks.id", "decks.kind"],
        ),
        CheckConstraint("parent_kind = 'standard'", name="ck_deck_parent_kind"),
        CheckConstraint(
            "parent_id IS NULL OR parent_id <> id", name="ck_deck_not_self"
        ),
        CheckConstraint(
            "kind IN ('standard','filtered') AND (kind <> 'filtered' OR parent_id IS NULL)",
            name="ck_deck_kind",
        ),
        Index(
            "uq_deck_root_name",
            "collection_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NULL AND kind = 'standard'"),
        ),
        Index(
            "uq_deck_child_name",
            "collection_id",
            "parent_id",
            "name",
            unique=True,
            postgresql_where=text("parent_id IS NOT NULL AND kind = 'standard'"),
        ),
    )


class Note(Entity, Scoped, Base):
    __tablename__ = "notes"
    guid: Mapped[str] = mapped_column(String(100), default=lambda: str(uuid7()))
    note_type_id: Mapped[UUID] = mapped_column(ForeignKey("note_types.id"))
    fields: Mapped[dict] = mapped_column(JSONB)
    tags: Mapped[list] = mapped_column(JSONB, default=list)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "id", "note_type_id"),
        UniqueConstraint("collection_id", "guid"),
        CheckConstraint("revision > 0", name="ck_note_revision"),
    )


class Card(Entity, Scoped, Base):
    __tablename__ = "cards"
    note_id: Mapped[UUID] = mapped_column(Uuid)
    note_type_id: Mapped[UUID] = mapped_column(Uuid)
    card_template_id: Mapped[UUID] = mapped_column(Uuid)
    template_ord: Mapped[int] = mapped_column(Integer)
    deck_id: Mapped[UUID] = mapped_column(Uuid)
    deck_kind: Mapped[str] = mapped_column(String(16), default="standard")
    original_deck_id: Mapped[UUID | None] = mapped_column(Uuid)
    original_deck_kind: Mapped[str] = mapped_column(String(16), default="standard")
    type: Mapped[str] = mapped_column(String(16), default="new")
    queue: Mapped[str] = mapped_column(String(20), default="new")
    new_position: Mapped[int | None] = mapped_column(BigInteger)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    due_day: Mapped[int | None] = mapped_column(Integer)
    fsrs_state: Mapped[dict | None] = mapped_column(JSONB)
    reps: Mapped[int] = mapped_column(Integer, default=0)
    lapses: Mapped[int] = mapped_column(Integer, default=0)
    learning_steps_remaining: Mapped[int] = mapped_column(Integer, default=0)
    interval_days: Mapped[float] = mapped_column(Float, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    buried_on_day: Mapped[int | None] = mapped_column(Integer)
    schedule_revision: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "id", "note_id", "card_template_id"),
        UniqueConstraint("collection_id", "note_id", "card_template_id"),
        ForeignKeyConstraint(
            ["collection_id", "note_id", "note_type_id"],
            ["notes.collection_id", "notes.id", "notes.note_type_id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["note_type_id", "card_template_id", "template_ord"],
            ["card_templates.note_type_id", "card_templates.id", "card_templates.ord"],
        ),
        ForeignKeyConstraint(
            ["collection_id", "deck_id", "deck_kind"],
            ["decks.collection_id", "decks.id", "decks.kind"],
        ),
        ForeignKeyConstraint(
            ["collection_id", "original_deck_id", "original_deck_kind"],
            ["decks.collection_id", "decks.id", "decks.kind"],
        ),
        CheckConstraint(
            "original_deck_kind = 'standard' AND ((deck_kind = 'standard' AND original_deck_id IS NULL) OR (deck_kind = 'filtered' AND original_deck_id IS NOT NULL))",
            name="ck_card_deck_kind",
        ),
        CheckConstraint(
            "type IN ('new','learning','review','relearning')", name="ck_card_type"
        ),
        CheckConstraint(
            "queue IN ('new','learning','day_learning','review','suspended','buried_user','buried_sibling')",
            name="ck_card_queue",
        ),
        CheckConstraint(
            "(type = 'new' AND new_position IS NOT NULL AND due_at IS NULL AND due_day IS NULL) OR (type = 'review' AND new_position IS NULL AND due_at IS NULL AND due_day IS NOT NULL) OR (type IN ('learning','relearning') AND new_position IS NULL AND ((due_at IS NOT NULL AND due_day IS NULL) OR (due_at IS NULL AND due_day IS NOT NULL)))",
            name="ck_card_due",
        ),
        CheckConstraint(
            "queue IN ('suspended','buried_user','buried_sibling') OR (queue = 'new' AND type = 'new') OR (queue = 'review' AND type = 'review') OR (queue = 'learning' AND type IN ('learning','relearning') AND due_at IS NOT NULL) OR (queue = 'day_learning' AND type IN ('learning','relearning') AND due_day IS NOT NULL)",
            name="ck_card_queue_type",
        ),
        CheckConstraint(
            "reps >= 0 AND lapses >= 0 AND schedule_revision >= 0 AND (new_position IS NULL OR new_position >= 0)",
            name="ck_card_counters",
        ),
        Index("ix_card_due", "collection_id", "queue", "due_day", "due_at"),
    )


class MediaAsset(Entity, Scoped, Base):
    __tablename__ = "media_assets"
    collection_kind: Mapped[str] = mapped_column(String(16), default="user")
    object_key: Mapped[str] = mapped_column(String(600), unique=True)
    kind: Mapped[str] = mapped_column(String(16))
    scope: Mapped[str] = mapped_column(String(16), default="private")
    lifecycle: Mapped[str] = mapped_column(String(20), default="ready")
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_type: Mapped[str | None] = mapped_column(String(80))
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "id", "scope"),
        ForeignKeyConstraint(
            ["collection_id", "collection_kind"], ["collections.id", "collections.kind"]
        ),
        CheckConstraint(
            "(scope = 'private' AND collection_kind = 'user') OR (scope = 'library_shared' AND collection_kind = 'library')",
            name="ck_media_owner_kind",
        ),
        CheckConstraint("kind IN ('audio','image')", name="ck_media_kind"),
        CheckConstraint("scope IN ('private','library_shared')", name="ck_media_scope"),
        CheckConstraint(
            "lifecycle IN ('temporary','ready','pending_delete')",
            name="ck_media_lifecycle",
        ),
    )


class MediaReference(Entity, Scoped, Base):
    __tablename__ = "media_references"
    note_id: Mapped[UUID] = mapped_column(Uuid)
    field_key: Mapped[str] = mapped_column(String(32))
    media_asset_id: Mapped[UUID] = mapped_column(Uuid)
    media_collection_id: Mapped[UUID] = mapped_column(Uuid)
    media_scope: Mapped[str] = mapped_column(String(16))
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "note_id", "field_key"),
        ForeignKeyConstraint(
            ["collection_id", "note_id"],
            ["notes.collection_id", "notes.id"],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["media_collection_id", "media_asset_id", "media_scope"],
            ["media_assets.collection_id", "media_assets.id", "media_assets.scope"],
        ),
        CheckConstraint(
            "media_scope = 'library_shared' OR media_collection_id = collection_id",
            name="ck_private_media_scope",
        ),
    )


class Attempt(Entity, Scoped, Base):
    """Snapshot persistence seam; creation/rating endpoints belong to LAN-32."""

    __tablename__ = "attempts"
    card_id: Mapped[UUID] = mapped_column(Uuid)
    note_id: Mapped[UUID] = mapped_column(Uuid)
    card_template_id: Mapped[UUID] = mapped_column(Uuid)
    review_token: Mapped[UUID] = mapped_column(Uuid, default=uuid7)
    note_snapshot: Mapped[dict] = mapped_column(JSONB)
    front_snapshot: Mapped[dict] = mapped_column(JSONB)
    back_snapshot: Mapped[dict] = mapped_column(JSONB)
    answer_snapshot: Mapped[dict] = mapped_column(JSONB)
    input_type: Mapped[str] = mapped_column(String(16))
    input_snapshot: Mapped[dict] = mapped_column(JSONB)
    media_asset_id: Mapped[UUID | None] = mapped_column(Uuid)
    rating: Mapped[str | None] = mapped_column(String(16))
    rated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    asr_status: Mapped[str] = mapped_column(String(16), default="skipped")
    asr_result: Mapped[dict | None] = mapped_column(JSONB)
    ai_status: Mapped[str] = mapped_column(String(16), default="skipped")
    ai_feedback: Mapped[dict | None] = mapped_column(JSONB)
    deterministic_result: Mapped[dict | None] = mapped_column(JSONB)
    card_schedule_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    quota_kind: Mapped[str | None] = mapped_column(String(16))
    quota_deck_id: Mapped[UUID | None] = mapped_column(Uuid)
    rating_result: Mapped[dict | None] = mapped_column(JSONB)
    previous_interval_days: Mapped[float | None] = mapped_column(Float)
    scheduled_interval_days: Mapped[float | None] = mapped_column(Float)
    review_kind: Mapped[str | None] = mapped_column(String(16))
    fsrs_algorithm_version: Mapped[str | None] = mapped_column(String(40))
    fsrs_config_version: Mapped[str | None] = mapped_column(String(64))
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "review_token"),
        ForeignKeyConstraint(
            ["collection_id", "card_id", "note_id", "card_template_id"],
            [
                "cards.collection_id",
                "cards.id",
                "cards.note_id",
                "cards.card_template_id",
            ],
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["collection_id", "media_asset_id"],
            ["media_assets.collection_id", "media_assets.id"],
        ),
        CheckConstraint(
            "input_type IN ('none','audio','text')", name="ck_attempt_input"
        ),
        CheckConstraint(
            "rating IS NULL OR rating IN ('again','hard','good','easy')",
            name="ck_attempt_rating",
        ),
        CheckConstraint(
            "(rating IS NULL) = (rated_at IS NULL)", name="ck_attempt_rated_at"
        ),
        Index(
            "uq_unrated_attempt",
            "collection_id",
            unique=True,
            postgresql_where=text("rating IS NULL"),
        ),
    )


class LegacyImport(Base):
    """Maintenance-only immutable import ledger; never exposed through content APIs."""

    __tablename__ = "legacy_imports"
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    checksum: Mapped[str] = mapped_column(String(64))
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow
    )
    report: Mapped[dict] = mapped_column(JSONB)
    archive: Mapped[dict] = mapped_column(JSONB)


class ReviewReceipt(Entity, Scoped, Base):
    """Durable idempotency receipts, never a persistent runtime queue."""
    __tablename__ = "review_receipts"
    key: Mapped[UUID] = mapped_column(Uuid)
    operation: Mapped[str] = mapped_column(String(100))
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("collection_id", "key"),)


class ProcessingOutbox(Entity, Scoped, Base):
    __tablename__ = "processing_outbox"
    attempt_id: Mapped[UUID] = mapped_column(Uuid)
    kind: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    __table_args__ = (
        UniqueConstraint("attempt_id", "kind"),
        ForeignKeyConstraint(["collection_id", "attempt_id"], ["attempts.collection_id", "attempts.id"], ondelete="CASCADE"),
        CheckConstraint("kind IN ('asr','ai')", name="ck_outbox_kind"),
    )


class DialogueSession(Entity, Scoped, Base):
    """A scenario snapshot and transcript, independent of Card scheduling."""
    __tablename__ = "dialogue_sessions"
    entry_key: Mapped[UUID] = mapped_column(Uuid)
    deck_id: Mapped[UUID] = mapped_column(Uuid)
    context: Mapped[dict] = mapped_column(JSONB)
    scenario: Mapped[dict] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(20), default="ready")
    finish_reason: Mapped[str | None] = mapped_column(String(30))
    user_turns: Mapped[int] = mapped_column(Integer, default=0)
    connection_id: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("collection_id", "id"),
        UniqueConstraint("collection_id", "entry_key"),
        CheckConstraint("status IN ('ready','active','interrupted','finished')", name="ck_dialogue_status"),
        CheckConstraint("user_turns >= 0 AND user_turns <= 8", name="ck_dialogue_turn_limit"),
    )


class DialogueTurn(Entity, Scoped, Base):
    __tablename__ = "dialogue_turns"
    session_id: Mapped[UUID] = mapped_column(Uuid)
    provider_item_id: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(16))
    text: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "session_id"], ["dialogue_sessions.collection_id", "dialogue_sessions.id"], ondelete="CASCADE"),
        UniqueConstraint("session_id", "provider_item_id", "role"),
        CheckConstraint("role IN ('user','assistant')", name="ck_dialogue_turn_role"),
    )


class DialogueReview(Entity, Scoped, Base):
    __tablename__ = "dialogue_reviews"
    session_id: Mapped[UUID] = mapped_column(Uuid, unique=True)
    result: Mapped[dict] = mapped_column(JSONB)
    __table_args__ = (
        ForeignKeyConstraint(["collection_id", "session_id"], ["dialogue_sessions.collection_id", "dialogue_sessions.id"], ondelete="CASCADE"),
    )
