"""private_beta_invites

Revision ID: a8f2d4c6e9b1
Revises: e4a9c1d2b3f0
Create Date: 2026-05-01 22:15:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a8f2d4c6e9b1"
down_revision: Union[str, Sequence[str], None] = "e4a9c1d2b3f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "invitation_codes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("max_uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("disabled_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(op.f("ix_invitation_codes_code"), "invitation_codes", ["code"], unique=False)
    op.create_index(op.f("ix_invitation_codes_id"), "invitation_codes", ["id"], unique=False)

    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("email_verified_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("invitation_code_id", sa.Integer(), nullable=True))
        batch_op.create_foreign_key(
            "fk_users_invitation_code_id_invitation_codes",
            "invitation_codes",
            ["invitation_code_id"],
            ["id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_constraint(
            "fk_users_invitation_code_id_invitation_codes",
            type_="foreignkey",
        )
        batch_op.drop_column("invitation_code_id")
        batch_op.drop_column("email_verified_at")

    op.drop_index(op.f("ix_invitation_codes_id"), table_name="invitation_codes")
    op.drop_index(op.f("ix_invitation_codes_code"), table_name="invitation_codes")
    op.drop_table("invitation_codes")
