"""beijing_time_business_local

Revision ID: ba4e3d9c8f21
Revises: 6f8b5f7d3a2e
Create Date: 2026-03-22 23:00:00.000000+00:00

"""

from datetime import UTC, datetime
from typing import Sequence, Union
from zoneinfo import ZoneInfo

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "ba4e3d9c8f21"
down_revision: Union[str, Sequence[str], None] = "6f8b5f7d3a2e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
BEIJING_TIMEZONE_NAME = "Asia/Shanghai"

TIME_COLUMNS: dict[str, tuple[list[str], list[str]]] = {
    "decks": (["id"], ["created_at", "updated_at"]),
    "cards": (["id"], ["created_at", "updated_at"]),
    "users": (["id"], ["created_at", "updated_at"]),
    "settings": (["key"], ["updated_at"]),
    "review_log": (["id"], ["created_at"]),
    "user_card_srs": (["card_id"], ["due", "last_review", "updated_at"]),
    "fsrs_review_log": (["id"], ["review_datetime"]),
}


def _to_business_local_naive(value: datetime, business_timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    else:
        value = value.astimezone(UTC)
    return value.astimezone(business_timezone).replace(tzinfo=None)


def _to_utc_naive(value: datetime, business_timezone: ZoneInfo) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=business_timezone)
    else:
        value = value.astimezone(business_timezone)
    return value.astimezone(UTC).replace(tzinfo=None)


def _convert_table_datetimes(
    bind: sa.Connection,
    *,
    table_name: str,
    primary_keys: list[str],
    datetime_columns: list[str],
    converter,
    timezone_value: ZoneInfo,
) -> None:
    metadata = sa.MetaData()
    table = sa.Table(table_name, metadata, autoload_with=bind)

    selected_columns = [table.c[column] for column in [*primary_keys, *datetime_columns]]
    rows = bind.execute(sa.select(*selected_columns)).mappings().all()

    for row in rows:
        updates: dict[str, datetime | None] = {}
        for column in datetime_columns:
            current_value = row[column]
            if current_value is None:
                continue
            updates[column] = converter(current_value, timezone_value)

        if not updates:
            continue

        predicate = sa.and_(*(table.c[key] == row[key] for key in primary_keys))
        bind.execute(sa.update(table).where(predicate).values(**updates))


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    business_timezone = ZoneInfo(BEIJING_TIMEZONE_NAME)

    for table_name, (primary_keys, datetime_columns) in TIME_COLUMNS.items():
        _convert_table_datetimes(
            bind,
            table_name=table_name,
            primary_keys=primary_keys,
            datetime_columns=datetime_columns,
            converter=_to_business_local_naive,
            timezone_value=business_timezone,
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    business_timezone = ZoneInfo(BEIJING_TIMEZONE_NAME)

    for table_name, (primary_keys, datetime_columns) in TIME_COLUMNS.items():
        _convert_table_datetimes(
            bind,
            table_name=table_name,
            primary_keys=primary_keys,
            datetime_columns=datetime_columns,
            converter=_to_utc_naive,
            timezone_value=business_timezone,
        )
