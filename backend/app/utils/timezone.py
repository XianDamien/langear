"""Fixed Beijing-time helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

APP_TIMEZONE = "Asia/Shanghai"
APP_ZONEINFO = ZoneInfo(APP_TIMEZONE)


def get_app_timezone(db: Session | None = None) -> ZoneInfo:
    """Return the fixed business timezone object."""
    del db
    return APP_ZONEINFO


def app_now(db: Session | None = None) -> datetime:
    """Return the current aware datetime in Beijing time."""
    return datetime.now(get_app_timezone(db))


def to_app_timezone(value: datetime, db: Session | None = None) -> datetime:
    """Convert aware or storage-local naive datetimes to Beijing time."""
    app_timezone = get_app_timezone(db)
    if value.tzinfo is None:
        return value.replace(tzinfo=app_timezone)
    return value.astimezone(app_timezone)


def to_utc(value: datetime, db: Session | None = None) -> datetime:
    """Convert aware or storage-local naive datetimes to aware UTC."""
    return to_app_timezone(value, db).astimezone(UTC)


def to_storage_local(value: datetime, db: Session | None = None) -> datetime:
    """Convert aware or local datetimes to storage-local naive values."""
    return to_app_timezone(value, db).replace(tzinfo=None)


def from_storage_local(value: datetime | None, db: Session | None = None) -> datetime | None:
    """Convert storage-local naive datetimes back to aware business-timezone values."""
    if value is None:
        return None
    return value.replace(tzinfo=get_app_timezone(db))


def storage_now(db: Session | None = None) -> datetime:
    """Return the current storage-local naive datetime."""
    return to_storage_local(app_now(db), db)


def app_day_window(
    value: date | datetime,
    db: Session | None = None,
) -> tuple[datetime, datetime]:
    """Return the storage-local naive window for a Beijing business day."""
    if isinstance(value, datetime):
        business_date = to_app_timezone(value, db).date()
    else:
        business_date = value

    app_timezone = get_app_timezone(db)
    day_start = datetime.combine(business_date, time.min, tzinfo=app_timezone)
    day_end = day_start + timedelta(days=1)
    return to_storage_local(day_start, db), to_storage_local(day_end, db)
