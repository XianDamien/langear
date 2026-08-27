"""fsrs_native_core

Revision ID: 6f8b5f7d3a2e
Revises: 16bdcd2b119f
Create Date: 2026-03-22 14:30:00.000000+00:00

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6f8b5f7d3a2e"
down_revision: Union[str, Sequence[str], None] = "16bdcd2b119f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "fsrs_review_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("review_datetime", sa.DateTime(), nullable=False),
        sa.Column("review_duration", sa.Integer(), nullable=True),
        sa.CheckConstraint("rating in (1, 2, 3, 4)", name="ck_fsrs_review_log_rating"),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_fsrs_review_log_card_id"), "fsrs_review_log", ["card_id"], unique=False)
    op.create_index(op.f("ix_fsrs_review_log_id"), "fsrs_review_log", ["id"], unique=False)
    op.create_index(
        op.f("ix_fsrs_review_log_review_datetime"),
        "fsrs_review_log",
        ["review_datetime"],
        unique=False,
    )

    with op.batch_alter_table("user_card_srs", schema=None) as batch_op:
        batch_op.add_column(sa.Column("step", sa.Integer(), nullable=True))
        batch_op.alter_column("stability", existing_type=sa.Float(), nullable=True)
        batch_op.alter_column("difficulty", existing_type=sa.Float(), nullable=True)

    op.execute(
        sa.text(
            """
            UPDATE user_card_srs
            SET state = 'learning',
                step = 0,
                stability = NULL,
                difficulty = NULL,
                last_review = NULL
            WHERE state = 'new'
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE user_card_srs
            SET step = 0
            WHERE state IN ('learning', 'relearning')
              AND step IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE user_card_srs
            SET step = NULL
            WHERE state = 'review'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO user_card_srs (
                card_id,
                state,
                step,
                stability,
                difficulty,
                due,
                last_review,
                updated_at
            )
            SELECT
                cards.id,
                'learning',
                0,
                NULL,
                NULL,
                cards.created_at,
                NULL,
                cards.created_at
            FROM cards
            LEFT JOIN user_card_srs ON user_card_srs.card_id = cards.id
            WHERE user_card_srs.card_id IS NULL
            """
        )
    )

    with op.batch_alter_table("user_card_srs", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "ck_user_card_srs_state",
            "state in ('learning', 'review', 'relearning')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("user_card_srs", schema=None) as batch_op:
        batch_op.drop_constraint("ck_user_card_srs_state", type_="check")

    op.execute(
        sa.text(
            """
            UPDATE user_card_srs
            SET state = 'new',
                step = NULL,
                stability = 0.0,
                difficulty = 5.0,
                last_review = NULL
            WHERE last_review IS NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE user_card_srs
            SET stability = COALESCE(stability, 0.0),
                difficulty = COALESCE(difficulty, 0.0)
            """
        )
    )

    with op.batch_alter_table("user_card_srs", schema=None) as batch_op:
        batch_op.alter_column("stability", existing_type=sa.Float(), nullable=False)
        batch_op.alter_column("difficulty", existing_type=sa.Float(), nullable=False)
        batch_op.drop_column("step")

    op.drop_index(op.f("ix_fsrs_review_log_review_datetime"), table_name="fsrs_review_log")
    op.drop_index(op.f("ix_fsrs_review_log_id"), table_name="fsrs_review_log")
    op.drop_index(op.f("ix_fsrs_review_log_card_id"), table_name="fsrs_review_log")
    op.drop_table("fsrs_review_log")
