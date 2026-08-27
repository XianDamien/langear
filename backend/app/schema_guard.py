"""Runtime schema validation for file-backed databases."""

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.config import BACKEND_ROOT, settings
from app.database import engine

REQUIRED_TABLE_COLUMNS = {
    "users": {
        "id",
        "username",
        "email",
        "email_verified_at",
        "password_hash",
        "invitation_code_id",
        "created_at",
        "updated_at",
    },
    "invitation_codes": {
        "id",
        "code",
        "note",
        "max_uses",
        "used_count",
        "expires_at",
        "disabled_at",
        "created_at",
        "updated_at",
    },
    "review_log": {
        "user_id",
        "user_deck_id",
        "ai_status",
        "submitted_rating",
        "rated_at",
    },
    "user_settings": {
        "user_id",
        "desired_retention",
        "learning_steps_json",
        "relearning_steps_json",
        "maximum_interval",
        "default_source_scope_json",
        "created_at",
        "updated_at",
    },
    "user_decks": {
        "id",
        "user_id",
        "origin_deck_id",
        "scope_type",
        "title_snapshot",
        "status",
        "created_at",
        "updated_at",
    },
    "user_deck_cards": {
        "user_deck_id",
        "card_id",
        "new_position",
        "created_at",
    },
    "user_card_fsrs": {
        "user_id",
        "card_id",
        "state",
        "step",
        "stability",
        "difficulty",
        "due",
        "last_review",
        "last_rating",
        "updated_at",
    },
    "user_card_srs": {
        "card_id",
        "state",
        "step",
        "stability",
        "difficulty",
        "due",
        "last_review",
        "updated_at",
    },
    "fsrs_review_log": set(),
}
REQUIRED_INDEX_COLUMNS = {
    "review_log": {
        ("ai_status",),
        ("user_deck_id",),
        ("user_id",),
    },
    "user_decks": {
        ("id",),
        ("origin_deck_id",),
        ("user_id",),
        ("user_id", "status"),
    },
    "user_card_fsrs": {
        ("card_id",),
        ("due",),
        ("user_id",),
        ("user_id", "state", "due"),
    },
}
SUGGESTED_FIX_COMMAND = "cd backend && uv run alembic upgrade head"


class SchemaValidationError(RuntimeError):
    """Raised when the runtime database schema is behind the code."""


@dataclass
class SchemaValidationResult:
    """Collected schema validation facts for runtime checks."""

    current_revision: str | None
    expected_revision: str
    missing_tables: list[str]
    missing_columns: dict[str, list[str]]
    missing_indexes: dict[str, list[tuple[str, ...]]]


def should_validate_runtime_schema(db_engine: Engine) -> bool:
    """Only enforce strict validation for persistent databases."""
    url = db_engine.url
    if url.drivername != "sqlite":
        return True
    return bool(url.database and url.database != ":memory:")


def get_expected_revision() -> str:
    """Return the Alembic head revision from the local migrations directory."""
    alembic_config = Config(str(BACKEND_ROOT / "alembic.ini"))
    alembic_config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(alembic_config).get_current_head()


def get_current_revision(db_engine: Engine) -> str | None:
    """Return the current database revision, if tracked."""
    inspector = inspect(db_engine)
    if "alembic_version" not in inspector.get_table_names():
        return None

    with db_engine.connect() as connection:
        row = connection.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
    return None if row is None else str(row[0])


def collect_missing_schema(db_engine: Engine) -> tuple[list[str], dict[str, list[str]]]:
    """Collect missing required tables and columns."""
    inspector = inspect(db_engine)
    table_names = set(inspector.get_table_names())

    missing_tables: list[str] = []
    missing_columns: dict[str, list[str]] = {}

    for table_name, required_columns in REQUIRED_TABLE_COLUMNS.items():
        if table_name not in table_names:
            missing_tables.append(table_name)
            continue

        if not required_columns:
            continue

        existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
        missing = sorted(required_columns - existing_columns)
        if missing:
            missing_columns[table_name] = missing

    return missing_tables, missing_columns


def collect_missing_indexes(db_engine: Engine) -> dict[str, list[tuple[str, ...]]]:
    """Collect missing required indexes by column tuple."""
    inspector = inspect(db_engine)
    table_names = set(inspector.get_table_names())
    missing_indexes: dict[str, list[tuple[str, ...]]] = {}

    for table_name, required_indexes in REQUIRED_INDEX_COLUMNS.items():
        if table_name not in table_names:
            continue

        existing_indexes = {
            tuple(index["column_names"] or [])
            for index in inspector.get_indexes(table_name)
        }
        missing = sorted(required_indexes - existing_indexes)
        if missing:
            missing_indexes[table_name] = missing

    return missing_indexes


def inspect_runtime_schema(db_engine: Engine | None = None) -> SchemaValidationResult | None:
    """Inspect schema state for the configured runtime database."""
    runtime_engine = db_engine or engine
    if not should_validate_runtime_schema(runtime_engine):
        return None

    expected_revision = get_expected_revision()
    current_revision = get_current_revision(runtime_engine)
    missing_tables, missing_columns = collect_missing_schema(runtime_engine)
    missing_indexes = collect_missing_indexes(runtime_engine)
    return SchemaValidationResult(
        current_revision=current_revision,
        expected_revision=expected_revision,
        missing_tables=missing_tables,
        missing_columns=missing_columns,
        missing_indexes=missing_indexes,
    )


def format_schema_validation_error(result: SchemaValidationResult) -> str:
    """Build a human-friendly schema mismatch message."""
    database_url = settings.resolved_database_url
    lines = [
        "Runtime database schema is out of date.",
        f"Database URL: {database_url}",
        f"Current DB revision: {result.current_revision or 'missing'}",
        f"Expected DB revision: {result.expected_revision}",
    ]

    if result.missing_tables:
        lines.append(f"Missing tables: {', '.join(result.missing_tables)}")

    if result.missing_columns:
        formatted_columns = ", ".join(
            f"{table}({', '.join(columns)})"
            for table, columns in sorted(result.missing_columns.items())
        )
        lines.append(f"Missing columns: {formatted_columns}")

    if result.missing_indexes:
        formatted_indexes = ", ".join(
            f"{table}({', '.join(columns)})"
            for table, indexes in sorted(result.missing_indexes.items())
            for columns in indexes
        )
        lines.append(f"Missing indexes: {formatted_indexes}")

    lines.append(f"Suggested fix: {SUGGESTED_FIX_COMMAND}")
    return "\n".join(lines)


def validate_runtime_schema(db_engine: Engine | None = None) -> None:
    """Abort startup when the runtime schema does not match the code."""
    result = inspect_runtime_schema(db_engine)
    if result is None:
        return

    if (
        result.current_revision != result.expected_revision
        or result.missing_tables
        or result.missing_columns
        or result.missing_indexes
    ):
        raise SchemaValidationError(format_schema_validation_error(result))
