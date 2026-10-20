"""Add invite registration, global default deck scope and daily activity history."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "lan33_0011"
down_revision = "lan21_0010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "invitation_codes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False, unique=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "max_uses > 0 AND used_count >= 0 AND used_count <= max_uses",
            name="ck_invitation_usage",
        ),
    )
    op.add_column(
        "users", sa.Column("invitation_code_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "fk_users_invitation_code",
        "users",
        "invitation_codes",
        ["invitation_code_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_user_username_normalized",
        "users",
        "username IS NULL OR username = lower(trim(username))",
    )
    op.add_column(
        "collections",
        sa.Column("default_deck_scope", JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "decks",
        sa.Column(
            "source_metadata", JSONB(), nullable=False, server_default="{}"
        ),
    )
    op.add_column(
        "decks",
        sa.Column("imported", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notes",
        sa.Column("imported", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "notes",
        sa.Column(
            "source_metadata", JSONB(), nullable=False, server_default="{}"
        ),
    )
    # Existing imported rows are backfilled from the identifiers written by the
    # one-shot importer, so runtime code can stop parsing `deck_guid`/`guid`.
    op.execute(
        "UPDATE decks SET imported = true WHERE deck_guid LIKE 'legacy:%'"
    )
    op.execute("UPDATE notes SET imported = true WHERE guid LIKE 'legacy:%'")
    op.create_table(
        "daily_activities",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("activity_date", sa.Date(), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False, server_default="legacy"),
        sa.Column("source_key", sa.String(160), nullable=False),
        sa.Column("reviews", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_cards", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collections.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint("collection_id", "source_key"),
        sa.CheckConstraint(
            "origin IN ('legacy','core')", name="ck_daily_activity_origin"
        ),
        sa.CheckConstraint(
            "reviews >= 0 AND new_cards >= 0", name="ck_daily_activity_counters"
        ),
    )
    op.create_index(
        "ix_daily_activity_date",
        "daily_activities",
        ["collection_id", "activity_date"],
    )
    op.create_index(
        "ix_daily_activities_collection_id",
        "daily_activities",
        ["collection_id"],
    )


def downgrade():
    op.drop_index("ix_daily_activities_collection_id", table_name="daily_activities")
    op.drop_index("ix_daily_activity_date", table_name="daily_activities")
    op.drop_table("daily_activities")
    op.drop_column("notes", "source_metadata")
    op.drop_column("notes", "imported")
    op.drop_column("decks", "imported")
    op.drop_column("decks", "source_metadata")
    op.drop_column("collections", "default_deck_scope")
    op.drop_constraint("ck_user_username_normalized", "users", type_="check")
    op.drop_constraint("fk_users_invitation_code", "users", type_="foreignkey")
    op.drop_column("users", "invitation_code_id")
    op.drop_table("invitation_codes")
