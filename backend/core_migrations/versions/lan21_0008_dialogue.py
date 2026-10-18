"""Independent Dialogue Session, Turn and Review storage; no scheduling changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = 'lan21_0008'
down_revision = 'lan32_0007'
branch_labels = depends_on = None


def entity():
    return [sa.Column('id', sa.Uuid(), primary_key=True),
            sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('collection_id', sa.Uuid(), sa.ForeignKey('collections.id', ondelete='CASCADE'), nullable=False, index=True)]


def upgrade():
    op.create_table('dialogue_sessions', *entity(),
        sa.Column('entry_key', sa.Uuid(), nullable=False), sa.Column('deck_id', sa.Uuid(), nullable=False),
        sa.Column('context', JSONB, nullable=False), sa.Column('scenario', JSONB, nullable=False),
        sa.Column('status', sa.String(20), nullable=False), sa.Column('finish_reason', sa.String(30)),
        sa.Column('user_turns', sa.Integer(), nullable=False), sa.Column('connection_id', sa.Uuid()),
        sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('collection_id', 'id'), sa.UniqueConstraint('collection_id', 'entry_key'),
        sa.CheckConstraint("status IN ('ready','active','interrupted','finished')", name='ck_dialogue_status'),
        sa.CheckConstraint('user_turns >= 0 AND user_turns <= 8', name='ck_dialogue_turn_limit'))
    op.create_table('dialogue_turns', *entity(), sa.Column('session_id', sa.Uuid(), nullable=False),
        sa.Column('provider_item_id', sa.String(200), nullable=False), sa.Column('role', sa.String(16), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(['collection_id','session_id'], ['dialogue_sessions.collection_id','dialogue_sessions.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('session_id','provider_item_id','role'),
        sa.CheckConstraint("role IN ('user','assistant')", name='ck_dialogue_turn_role'))
    op.create_table('dialogue_reviews', *entity(), sa.Column('session_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('result', JSONB, nullable=False),
        sa.ForeignKeyConstraint(['collection_id','session_id'], ['dialogue_sessions.collection_id','dialogue_sessions.id'], ondelete='CASCADE'))


def downgrade():
    for name in ('dialogue_reviews', 'dialogue_turns', 'dialogue_sessions'):
        op.drop_table(name)
