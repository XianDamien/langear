"""Helpers for resolving backend database URLs."""

from pathlib import Path


DEFAULT_RELATIVE_SQLITE_URL = "sqlite:///data/langear.db"


def resolve_database_url(database_url: str, *, base_dir: Path) -> str:
    """Resolve relative SQLite URLs against a stable base directory."""
    normalized = database_url.strip()
    sqlite_prefix = "sqlite:///"
    if not normalized.startswith(sqlite_prefix):
        return normalized

    database_path = normalized[len(sqlite_prefix) :]
    if not database_path or database_path == ":memory:" or database_path.startswith("/"):
        return normalized

    resolved_path = (base_dir / database_path).resolve()
    return f"sqlite:///{resolved_path}"


def build_default_sqlite_database_url(base_dir: Path) -> str:
    """Build the default SQLite URL anchored to the given base directory."""
    return resolve_database_url(DEFAULT_RELATIVE_SQLITE_URL, base_dir=base_dir)
