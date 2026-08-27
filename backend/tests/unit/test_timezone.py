"""Unit tests for fixed Beijing-time helpers."""

from datetime import UTC, date, datetime

import pytest

from app.utils.timezone import app_day_window, from_storage_local, to_storage_local


@pytest.mark.unit
def test_timezone_helpers_use_fixed_beijing_time():
    utc_value = datetime(2026, 3, 22, 12, 30, tzinfo=UTC)
    storage_value = to_storage_local(utc_value)
    restored_value = from_storage_local(storage_value)

    assert storage_value == datetime(2026, 3, 22, 20, 30)
    assert restored_value.isoformat() == "2026-03-22T20:30:00+08:00"


@pytest.mark.unit
def test_app_day_window_uses_beijing_local_window():
    start, end = app_day_window(date(2026, 3, 22))

    assert start == datetime(2026, 3, 22, 0, 0)
    assert end == datetime(2026, 3, 23, 0, 0)
