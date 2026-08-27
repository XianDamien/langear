"""Print the backend runtime database and CORS configuration."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

from sqlalchemy.engine import make_url

from app.database_url import DEFAULT_RELATIVE_SQLITE_URL, resolve_database_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_ROOT / ".env"
DEFAULT_CORS_ORIGINS = "http://localhost:3002,http://127.0.0.1:3002"


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _inspect_sqlite(sqlite_path: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "path": str(sqlite_path),
        "exists": sqlite_path.exists(),
    }
    if not sqlite_path.exists():
        return report

    with sqlite3.connect(sqlite_path) as conn:
        conn.row_factory = sqlite3.Row
        report["review_log_count"] = conn.execute("select count(*) from review_log").fetchone()[0]
        report["user_card_srs_count"] = conn.execute("select count(*) from user_card_srs").fetchone()[0]
        rows = conn.execute(
            """
            select id, status, result_type, deck_id, card_id, rating, error_code, created_at
            from review_log
            order by id desc
            limit 5
            """
        ).fetchall()
    report["latest_review_logs"] = [dict(row) for row in rows]
    return report


def main() -> None:
    env_file_values = _load_env_file(ENV_FILE)
    configured_database_url = (
        os.environ.get("DATABASE_URL")
        or env_file_values.get("DATABASE_URL")
        or DEFAULT_RELATIVE_SQLITE_URL
    )
    resolved_database_url = resolve_database_url(configured_database_url, base_dir=BACKEND_ROOT)
    configured_cors_origins = (
        os.environ.get("CORS_ORIGINS")
        or env_file_values.get("CORS_ORIGINS")
        or DEFAULT_CORS_ORIGINS
    )

    sqlite_path = None
    url = make_url(resolved_database_url)
    if url.drivername == "sqlite" and url.database and url.database != ":memory:":
        sqlite_path = Path(url.database).resolve()

    payload: dict[str, object] = {
        "cwd": str(Path.cwd()),
        "env_file": {
            "path": str(ENV_FILE),
            "exists": ENV_FILE.exists(),
        },
        "source_of_truth": {
            "review_feedback": "review_log.ai_feedback_json",
            "fsrs": "user_card_srs",
            "user_audio": "OSS",
            "offline_dataset_is_source_of_truth": False,
        },
        "database_url": {
            "configured": configured_database_url,
            "resolved": resolved_database_url,
            "sqlite_path": str(sqlite_path) if sqlite_path else None,
        },
        "cors_origins": [
            origin.strip()
            for origin in configured_cors_origins.split(",")
            if origin.strip()
        ],
    }
    if sqlite_path is not None:
        payload["sqlite"] = _inspect_sqlite(sqlite_path)

    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
