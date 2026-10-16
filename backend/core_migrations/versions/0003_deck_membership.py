"""Persist course membership for user-owned core decks."""
from alembic import op
import sqlalchemy as sa

revision = "lan30_0003"
down_revision = "lan30_0002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("decks", sa.Column("in_my_courses", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    op.drop_column("decks", "in_my_courses")
