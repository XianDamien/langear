"""Retain versioned rating audit facts independently from runtime Undo snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "lan32_0006"
down_revision = "lan31_0005"
branch_labels = None
depends_on = None


def upgrade():
    for name, kind in [
        ("previous_interval_days", sa.Float()),
        ("scheduled_interval_days", sa.Float()),
        ("review_kind", sa.String(16)),
        ("fsrs_algorithm_version", sa.String(40)),
        ("fsrs_config_version", sa.String(64)),
    ]:
        op.add_column("attempts", sa.Column(name, kind, nullable=True))


def downgrade():
    for name in [
        "previous_interval_days",
        "scheduled_interval_days",
        "review_kind",
        "fsrs_algorithm_version",
        "fsrs_config_version",
    ]:
        op.drop_column("attempts", name)
