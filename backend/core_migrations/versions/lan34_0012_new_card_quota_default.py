"""Raise the new-card quota default from 20 to 9999.

The old default was persisted into every Collection and into Decks that had
saved their settings. Rewriting only the exact old default keeps intentional
lower quotas (for example, vocabulary review decks at 5) untouched.
"""
from alembic import op

revision = "lan34_0012"
down_revision = "lan33_0011"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("collections", "decks"):
        op.execute(
            f"""
            UPDATE {table}
            SET scheduling_config = jsonb_set(
                scheduling_config, '{{new_limit}}', '9999'::jsonb
            )
            WHERE scheduling_config @> '{{"new_limit": 20}}'::jsonb
            """
        )


def downgrade():
    for table in ("collections", "decks"):
        op.execute(
            f"""
            UPDATE {table}
            SET scheduling_config = jsonb_set(
                scheduling_config, '{{new_limit}}', '20'::jsonb
            )
            WHERE scheduling_config @> '{{"new_limit": 9999}}'::jsonb
            """
        )
