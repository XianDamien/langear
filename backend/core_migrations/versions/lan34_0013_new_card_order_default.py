"""Default new cards to source order instead of a stable random order.

The old default was persisted into every Collection. Rewriting only that exact
value keeps Deck-level choices, such as a learner explicitly selecting random
order, untouched.
"""
from alembic import op

revision = "lan34_0013"
down_revision = "lan34_0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE collections
        SET scheduling_config = jsonb_set(
            scheduling_config,
            '{new_card_gather_order}',
            '"lowest_position"'::jsonb
        )
        WHERE scheduling_config @> '{"new_card_gather_order": "random_cards"}'::jsonb
        """
    )


def downgrade():
    op.execute(
        """
        UPDATE collections
        SET scheduling_config = jsonb_set(
            scheduling_config,
            '{new_card_gather_order}',
            '"random_cards"'::jsonb
        )
        WHERE scheduling_config @> '{"new_card_gather_order": "lowest_position"}'::jsonb
        """
    )
