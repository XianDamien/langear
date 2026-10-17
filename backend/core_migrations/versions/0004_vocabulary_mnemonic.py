"""Add optional vocabulary mnemonic and render it on card backs only."""
from uuid import uuid4
from alembic import op
import sqlalchemy as sa

revision = "lan30_0004"
down_revision = "lan30_0003"
branch_labels = None
depends_on = None


def upgrade():
    db = op.get_bind()
    db.execute(sa.text("""
        INSERT INTO note_type_fields (id, created_at, updated_at, note_type_id, key, ord, kind, required)
        SELECT :id, now(), now(), id, 'mnemonic', 6, 'text', false
        FROM note_types WHERE key = 'vocabulary'
        ON CONFLICT (note_type_id, key) DO NOTHING
    """), {"id": uuid4()})
    db.execute(sa.text("""
        UPDATE card_templates SET a_format = a_format || '["mnemonic"]'::jsonb,
            updated_at = now()
        WHERE key IN ('vocabulary_english_to_chinese', 'vocabulary_chinese_to_english')
            AND NOT (a_format ? 'mnemonic')
    """))


def downgrade():
    db = op.get_bind()
    db.execute(sa.text("""
        UPDATE card_templates SET a_format = a_format - 'mnemonic', updated_at = now()
        WHERE key IN ('vocabulary_english_to_chinese', 'vocabulary_chinese_to_english')
    """))
    db.execute(sa.text("""
        DELETE FROM note_type_fields WHERE key = 'mnemonic'
        AND note_type_id IN (SELECT id FROM note_types WHERE key = 'vocabulary')
    """))
    # Keep existing Note.fields / Attempt snapshots intact for a future re-upgrade.
