"""Tests for the fixed Beijing-time migration helpers."""

from __future__ import annotations

import importlib.util
from datetime import datetime
from pathlib import Path

import pytest
import sqlalchemy as sa


def _load_migration_module():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "migrations"
        / "versions"
        / "20260322_2300_ba4e3d9c8f21_app_timezone_business_local.py"
    )
    spec = importlib.util.spec_from_file_location("app_timezone_migration", migration_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.unit
def test_migration_converts_utc_naive_to_business_local_naive():
    module = _load_migration_module()

    converted = module._to_business_local_naive(
        datetime(2026, 3, 22, 12, 0, 0),
        module.ZoneInfo(module.BEIJING_TIMEZONE_NAME),
    )

    assert converted == datetime(2026, 3, 22, 20, 0, 0)


@pytest.mark.unit
def test_migration_updates_rows_without_writing_app_timezone_setting():
    module = _load_migration_module()
    engine = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    review_log = sa.Table(
        "review_log",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    settings = sa.Table(
        "settings",
        metadata,
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        connection.execute(
            sa.insert(review_log).values(id=1, created_at=datetime(2026, 3, 22, 12, 0, 0))
        )

        module._convert_table_datetimes(
            connection,
            table_name="review_log",
            primary_keys=["id"],
            datetime_columns=["created_at"],
            converter=module._to_business_local_naive,
            timezone_value=module.ZoneInfo(module.BEIJING_TIMEZONE_NAME),
        )

        converted_row = connection.execute(sa.select(review_log.c.created_at)).scalar_one()
        settings_rows = connection.execute(sa.select(settings.c.key)).all()

    assert converted_row == datetime(2026, 3, 22, 20, 0, 0)
    assert settings_rows == []
