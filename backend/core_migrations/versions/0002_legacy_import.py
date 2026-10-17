"""Add legacy usernames and a maintenance-only immutable import ledger."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "lan30_0002"
down_revision = "lan30_0001"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("users", "email", existing_type=sa.String(254), nullable=True)
    op.add_column("users", sa.Column("username", sa.String(100), nullable=True))
    op.create_unique_constraint("uq_users_username", "users", ["username"])
    op.create_table(
        "legacy_imports",
        sa.Column("source", sa.String(100), primary_key=True),
        sa.Column("checksum", sa.String(64), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("report", JSONB, nullable=False),
        sa.Column("archive", JSONB, nullable=False),
    )


def downgrade():
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM legacy_imports) OR EXISTS(SELECT 1 FROM users WHERE email IS NULL OR username IS NOT NULL)"
        )
    ):
        raise RuntimeError(
            "Imported accounts exist; restore the pre-import backup to roll back."
        )
    op.drop_table("legacy_imports")
    op.drop_constraint("uq_users_username", "users", type_="unique")
    op.drop_column("users", "username")
    op.alter_column("users", "email", existing_type=sa.String(254), nullable=False)
