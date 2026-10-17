"""Track verified learner audio uploads before an Attempt can claim them."""
from alembic import op
import sqlalchemy as sa
revision = "lan32_0007"
down_revision = "lan32_0006"
branch_labels = depends_on = None


def upgrade():
    op.add_column("media_assets", sa.Column("uploaded_at", sa.DateTime(timezone=True)))
    op.add_column("media_assets", sa.Column("content_type", sa.String(80)))
    op.add_column("media_assets", sa.Column("size_bytes", sa.Integer))


def downgrade():
    for name in ("size_bytes", "content_type", "uploaded_at"):
        op.drop_column("media_assets", name)
