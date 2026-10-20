"""Drop the fixed turn limit and cache pre-generated Chinese per turn."""
from alembic import op
import sqlalchemy as sa

revision = 'lan21_0010'
down_revision = 'lan21_0009'
branch_labels = depends_on = None


def upgrade():
    op.drop_constraint('ck_dialogue_turn_limit', 'dialogue_sessions', type_='check')
    op.add_column('dialogue_turns', sa.Column('translation_zh', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('dialogue_turns', 'translation_zh')
    op.create_check_constraint('ck_dialogue_turn_limit', 'dialogue_sessions', 'user_turns >= 0 AND user_turns <= 8')
