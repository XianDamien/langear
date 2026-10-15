"""Unit tests for runtime schema validation."""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.database import Base
from app.schema_guard import (
    SchemaValidationError,
    collect_missing_schema,
    get_expected_revision,
    inspect_runtime_schema,
    should_validate_runtime_schema,
    validate_runtime_schema,
)

# Ensure all ORM models are registered on Base.metadata.
from app.models import (  # noqa: F401
    Card,
    Deck,
    FSRSReviewLog,
    InvitationCode,
    ReviewLog,
    Setting,
    User,
    UserCardFSRS,
    UserCardSRS,
    UserDeck,
    UserDeckCard,
    UserSettings,
)


def _create_file_engine(db_path: Path):
    return create_engine(f"sqlite:///{db_path}")


@pytest.mark.unit
def test_validate_runtime_schema_passes_for_current_schema(tmp_path: Path):
    db_path = tmp_path / "schema_ok.db"
    engine = _create_file_engine(db_path)
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES (:revision)"),
            {"revision": get_expected_revision()},
        )

    validate_runtime_schema(engine)


@pytest.mark.unit
def test_validate_runtime_schema_rejects_stale_revision_and_missing_columns(tmp_path: Path):
    db_path = tmp_path / "schema_stale.db"
    engine = _create_file_engine(db_path)

    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
        connection.execute(
            text("INSERT INTO alembic_version (version_num) VALUES ('16bdcd2b119f')")
        )
        connection.execute(
            text(
                """
                CREATE TABLE user_card_srs (
                    card_id INTEGER NOT NULL PRIMARY KEY,
                    state VARCHAR(20) NOT NULL,
                    stability FLOAT NOT NULL,
                    difficulty FLOAT NOT NULL,
                    due DATETIME NOT NULL,
                    last_review DATETIME,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE review_log (
                    id INTEGER NOT NULL PRIMARY KEY,
                    card_id INTEGER,
                    deck_id INTEGER NOT NULL,
                    rating VARCHAR(20),
                    result_type VARCHAR(20) NOT NULL,
                    ai_feedback_json JSON NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_code VARCHAR(50),
                    error_message TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    with pytest.raises(SchemaValidationError) as exc_info:
        validate_runtime_schema(engine)

    error_message = str(exc_info.value)
    assert "Runtime database schema is out of date." in error_message
    assert "Database URL:" in error_message
    assert "Current DB revision: 16bdcd2b119f" in error_message
    assert f"Expected DB revision: {get_expected_revision()}" in error_message
    assert "Missing tables:" in error_message
    for table_name in [
        "fsrs_review_log",
        "invitation_codes",
        "users",
        "user_settings",
        "user_decks",
        "user_deck_cards",
        "user_card_fsrs",
    ]:
        assert table_name in error_message
    assert "Missing columns:" in error_message
    assert "review_log(ai_status, rated_at, submitted_rating, user_deck_id, user_id)" in error_message
    assert "user_card_srs(step)" in error_message
    assert "uv run alembic upgrade head" in error_message


@pytest.mark.unit
def test_in_memory_sqlite_skips_runtime_schema_validation():
    engine = create_engine("sqlite:///:memory:")

    assert should_validate_runtime_schema(engine) is False
    assert inspect_runtime_schema(engine) is None


@pytest.mark.unit
def test_collect_missing_schema_reports_only_required_drift(tmp_path: Path):
    db_path = tmp_path / "schema_partial.db"
    engine = _create_file_engine(db_path)

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE user_card_srs (
                    card_id INTEGER NOT NULL PRIMARY KEY,
                    state VARCHAR(20) NOT NULL,
                    step INTEGER,
                    due DATETIME NOT NULL,
                    last_review DATETIME,
                    updated_at DATETIME NOT NULL
                )
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE TABLE review_log (
                    id INTEGER NOT NULL PRIMARY KEY,
                    card_id INTEGER,
                    deck_id INTEGER NOT NULL,
                    rating VARCHAR(20),
                    result_type VARCHAR(20) NOT NULL,
                    ai_feedback_json JSON NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    error_code VARCHAR(50),
                    error_message TEXT,
                    created_at DATETIME NOT NULL
                )
                """
            )
        )

    missing_tables, missing_columns = collect_missing_schema(engine)

    assert missing_tables == [
        "users",
        "invitation_codes",
        "user_settings",
        "user_decks",
        "user_deck_cards",
        "user_card_fsrs",
        "fsrs_review_log",
    ]
    assert missing_columns == {
        "review_log": ["ai_status", "rated_at", "submitted_rating", "user_deck_id", "user_id"],
        "user_card_srs": ["difficulty", "stability"],
    }
