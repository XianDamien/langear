"""Durable review receipts, input processing handoff and bury day."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "lan31_0005"
down_revision = "lan30_0004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("cards", sa.Column("buried_on_day", sa.Integer(), nullable=True))
    for column in [
        sa.Column(
            "card_schedule_revision", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("quota_kind", sa.String(16)),
        sa.Column("quota_deck_id", sa.Uuid()),
        sa.Column("rating_result", JSONB),
    ]:
        op.add_column("attempts", column)
    entity = lambda: [
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "collection_id",
            sa.Uuid(),
            sa.ForeignKey("collections.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
    ]
    op.create_table(
        "review_receipts",
        *entity(),
        sa.Column("key", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("response", JSONB, nullable=False),
        sa.UniqueConstraint("collection_id", "key"),
    )
    op.create_table(
        "processing_outbox",
        *entity(),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.UniqueConstraint("attempt_id", "kind"),
        sa.ForeignKeyConstraint(
            ["collection_id", "attempt_id"],
            ["attempts.collection_id", "attempts.id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("kind IN ('asr','ai')", name="ck_outbox_kind"),
    )


def downgrade():
    op.drop_table("processing_outbox")
    op.drop_table("review_receipts")
    for name in [
        "card_schedule_revision",
        "quota_kind",
        "quota_deck_id",
        "rating_result",
    ]:
        op.drop_column("attempts", name)
    op.drop_column("cards", "buried_on_day")
