"""Bounded processing retries with a durable backoff deadline."""
import sqlalchemy as sa
from alembic import op

revision = "lan32_0008"
down_revision = "lan32_0007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("processing_outbox", sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("processing_outbox", sa.Column("next_attempt_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_outbox_retry_count", "processing_outbox", "retry_count >= 0")
    op.create_index("ix_outbox_pending_due", "processing_outbox", ["status", "next_attempt_at", "created_at"])


def downgrade():
    op.drop_index("ix_outbox_pending_due", table_name="processing_outbox")
    op.drop_constraint("ck_outbox_retry_count", "processing_outbox", type_="check")
    op.drop_column("processing_outbox", "next_attempt_at")
    op.drop_column("processing_outbox", "retry_count")
