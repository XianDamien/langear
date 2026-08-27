"""user_deck_soft_delete_selection

Revision ID: 8f3c2d1a4b6e
Revises: a8f2d4c6e9b1
Create Date: 2026-05-04 20:15:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8f3c2d1a4b6e"
down_revision: Union[str, Sequence[str], None] = "a8f2d4c6e9b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("user_decks", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                sa.String(length=20),
                nullable=False,
                server_default="active",
            )
        )
        batch_op.create_check_constraint(
            "ck_user_decks_status",
            "status in ('active', 'inactive')",
        )
        batch_op.create_index(
            "ix_user_decks_user_id_status",
            ["user_id", "status"],
            unique=False,
        )

    with op.batch_alter_table("user_card_fsrs", schema=None) as batch_op:
        batch_op.create_index(
            "ix_user_card_fsrs_user_id_state_due",
            ["user_id", "state", "due"],
            unique=False,
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_card_fsrs", schema=None) as batch_op:
        batch_op.drop_index("ix_user_card_fsrs_user_id_state_due")

    with op.batch_alter_table("user_decks", schema=None) as batch_op:
        batch_op.drop_index("ix_user_decks_user_id_status")
        batch_op.drop_constraint("ck_user_decks_status", type_="check")
        batch_op.drop_column("status")
