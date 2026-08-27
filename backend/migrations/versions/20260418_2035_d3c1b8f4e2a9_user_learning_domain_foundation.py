"""user_learning_domain_foundation

Revision ID: d3c1b8f4e2a9
Revises: ba4e3d9c8f21
Create Date: 2026-04-18 20:35:00.000000+00:00

"""

from datetime import datetime
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d3c1b8f4e2a9"
down_revision: Union[str, Sequence[str], None] = "ba4e3d9c8f21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BUSINESS_TIMEZONE = ZoneInfo("Asia/Shanghai")


def _business_now() -> datetime:
    return datetime.now(BUSINESS_TIMEZONE).replace(tzinfo=None)


def upgrade() -> None:
    """Upgrade schema."""
    business_now = _business_now()

    op.create_table(
        "user_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("desired_retention", sa.Float(), nullable=False),
        sa.Column("learning_steps_json", sa.JSON(), nullable=False),
        sa.Column("relearning_steps_json", sa.JSON(), nullable=False),
        sa.Column("maximum_interval", sa.Integer(), nullable=False),
        sa.Column("default_source_scope_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "user_decks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("origin_deck_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(length=20), nullable=False),
        sa.Column("title_snapshot", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["origin_deck_id"], ["decks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "origin_deck_id", name="uq_user_decks_user_origin"),
    )
    op.create_index(op.f("ix_user_decks_id"), "user_decks", ["id"], unique=False)
    op.create_index(op.f("ix_user_decks_origin_deck_id"), "user_decks", ["origin_deck_id"], unique=False)
    op.create_index(op.f("ix_user_decks_user_id"), "user_decks", ["user_id"], unique=False)

    op.create_table(
        "user_deck_cards",
        sa.Column("user_deck_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("new_position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
        sa.ForeignKeyConstraint(["user_deck_id"], ["user_decks.id"]),
        sa.PrimaryKeyConstraint("user_deck_id", "card_id"),
        sa.UniqueConstraint("user_deck_id", "new_position", name="uq_user_deck_cards_position"),
    )
    op.create_index(op.f("ix_user_deck_cards_card_id"), "user_deck_cards", ["card_id"], unique=False)

    op.create_table(
        "user_card_fsrs",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("step", sa.Integer(), nullable=True),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("due", sa.DateTime(), nullable=False),
        sa.Column("last_review", sa.DateTime(), nullable=True),
        sa.Column("last_rating", sa.String(length=20), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "state in ('learning', 'review', 'relearning')",
            name="ck_user_card_fsrs_state",
        ),
        sa.ForeignKeyConstraint(["card_id"], ["cards.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("user_id", "card_id"),
    )
    op.create_index(op.f("ix_user_card_fsrs_card_id"), "user_card_fsrs", ["card_id"], unique=False)
    op.create_index(op.f("ix_user_card_fsrs_due"), "user_card_fsrs", ["due"], unique=False)
    op.create_index(op.f("ix_user_card_fsrs_user_id"), "user_card_fsrs", ["user_id"], unique=False)

    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("user_deck_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ai_status", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("submitted_rating", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("rated_at", sa.DateTime(), nullable=True))
        batch_op.alter_column("ai_feedback_json", existing_type=sa.JSON(), nullable=True)

    bind = op.get_bind()
    metadata = sa.MetaData()
    settings_table = sa.Table("settings", metadata, autoload_with=bind)
    user_settings_table = sa.Table("user_settings", metadata, autoload_with=bind)

    bind.execute(
        sa.text(
            """
            INSERT INTO users (id, username, email, created_at, updated_at)
            SELECT 1, 'default', NULL, :now, :now
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = 1)
            """
        ),
        {"now": business_now},
    )

    default_scope = bind.execute(
        sa.select(settings_table.c.value).where(settings_table.c.key == "default_source_scope")
    ).scalar_one_or_none()
    if default_scope is None:
        default_scope = []

    has_user_settings = bind.execute(
        sa.select(user_settings_table.c.user_id).where(user_settings_table.c.user_id == 1)
    ).first()
    if has_user_settings is None:
        bind.execute(
            user_settings_table.insert().values(
                user_id=1,
                desired_retention=0.9,
                learning_steps_json=[15],
                relearning_steps_json=[15],
                maximum_interval=36500,
                default_source_scope_json=default_scope,
                created_at=business_now,
                updated_at=business_now,
            )
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO user_decks (
                user_id,
                origin_deck_id,
                scope_type,
                title_snapshot,
                created_at,
                updated_at
            )
            SELECT
                1,
                traced.origin_deck_id,
                decks.type,
                decks.title,
                :now,
                :now
            FROM (
                SELECT DISTINCT cards.deck_id AS origin_deck_id
                FROM user_card_srs
                JOIN cards ON cards.id = user_card_srs.card_id
                WHERE user_card_srs.last_review IS NOT NULL
                UNION
                SELECT DISTINCT deck_id AS origin_deck_id
                FROM review_log
                WHERE deck_id IS NOT NULL
            ) AS traced
            JOIN decks ON decks.id = traced.origin_deck_id
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_decks
                WHERE user_decks.user_id = 1
                  AND user_decks.origin_deck_id = traced.origin_deck_id
            )
            """
        ),
        {"now": business_now},
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO user_deck_cards (
                user_deck_id,
                card_id,
                new_position,
                created_at
            )
            SELECT
                ordered_cards.user_deck_id,
                ordered_cards.card_id,
                ROW_NUMBER() OVER (
                    PARTITION BY ordered_cards.user_deck_id
                    ORDER BY ordered_cards.card_index, ordered_cards.card_id
                ),
                :now
            FROM (
                SELECT
                    user_decks.id AS user_deck_id,
                    cards.id AS card_id,
                    cards.card_index AS card_index
                FROM user_decks
                JOIN cards ON cards.deck_id = user_decks.origin_deck_id
                WHERE user_decks.user_id = 1
            ) AS ordered_cards
            WHERE NOT EXISTS (
                SELECT 1
                FROM user_deck_cards
                WHERE user_deck_cards.user_deck_id = ordered_cards.user_deck_id
                  AND user_deck_cards.card_id = ordered_cards.card_id
            )
            """
        ),
        {"now": business_now},
    )

    bind.execute(
        sa.text(
            """
            INSERT INTO user_card_fsrs (
                user_id,
                card_id,
                state,
                step,
                stability,
                difficulty,
                due,
                last_review,
                last_rating,
                updated_at
            )
            SELECT
                1,
                s.card_id,
                s.state,
                s.step,
                s.stability,
                s.difficulty,
                s.due,
                s.last_review,
                (
                    SELECT rl.rating
                    FROM review_log AS rl
                    WHERE rl.card_id = s.card_id
                      AND rl.result_type = 'single'
                      AND rl.rating IS NOT NULL
                    ORDER BY rl.created_at DESC, rl.id DESC
                    LIMIT 1
                ),
                s.updated_at
            FROM user_card_srs AS s
            WHERE s.last_review IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM user_card_fsrs
                  WHERE user_card_fsrs.user_id = 1
                    AND user_card_fsrs.card_id = s.card_id
              )
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE review_log
            SET user_id = 1,
                ai_status = CASE COALESCE(status, 'processing')
                    WHEN 'completed' THEN 'completed'
                    WHEN 'failed' THEN 'failed'
                    ELSE 'processing'
                END,
                submitted_rating = rating,
                rated_at = NULL
            """
        )
    )

    bind.execute(
        sa.text(
            """
            UPDATE review_log
            SET user_deck_id = (
                SELECT user_decks.id
                FROM user_decks
                WHERE user_decks.user_id = review_log.user_id
                  AND user_decks.origin_deck_id = review_log.deck_id
                LIMIT 1
            )
            WHERE deck_id IS NOT NULL
            """
        )
    )

    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False)
        batch_op.alter_column("ai_status", existing_type=sa.String(length=20), nullable=False)
        batch_op.create_foreign_key("fk_review_log_user_id_users", "users", ["user_id"], ["id"])
        batch_op.create_foreign_key(
            "fk_review_log_user_deck_id_user_decks",
            "user_decks",
            ["user_deck_id"],
            ["id"],
        )
        batch_op.create_index(op.f("ix_review_log_ai_status"), ["ai_status"], unique=False)
        batch_op.create_index(op.f("ix_review_log_user_deck_id"), ["user_deck_id"], unique=False)
        batch_op.create_index(op.f("ix_review_log_user_id"), ["user_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("review_log", schema=None) as batch_op:
        batch_op.drop_index(op.f("ix_review_log_user_id"))
        batch_op.drop_index(op.f("ix_review_log_user_deck_id"))
        batch_op.drop_index(op.f("ix_review_log_ai_status"))
        batch_op.drop_constraint("fk_review_log_user_deck_id_user_decks", type_="foreignkey")
        batch_op.drop_constraint("fk_review_log_user_id_users", type_="foreignkey")
        batch_op.alter_column("ai_feedback_json", existing_type=sa.JSON(), nullable=False)
        batch_op.drop_column("rated_at")
        batch_op.drop_column("submitted_rating")
        batch_op.drop_column("ai_status")
        batch_op.drop_column("user_deck_id")
        batch_op.drop_column("user_id")

    op.drop_index(op.f("ix_user_card_fsrs_user_id"), table_name="user_card_fsrs")
    op.drop_index(op.f("ix_user_card_fsrs_due"), table_name="user_card_fsrs")
    op.drop_index(op.f("ix_user_card_fsrs_card_id"), table_name="user_card_fsrs")
    op.drop_table("user_card_fsrs")

    op.drop_index(op.f("ix_user_deck_cards_card_id"), table_name="user_deck_cards")
    op.drop_table("user_deck_cards")

    op.drop_index(op.f("ix_user_decks_user_id"), table_name="user_decks")
    op.drop_index(op.f("ix_user_decks_origin_deck_id"), table_name="user_decks")
    op.drop_index(op.f("ix_user_decks_id"), table_name="user_decks")
    op.drop_table("user_decks")

    op.drop_table("user_settings")
