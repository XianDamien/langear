"""Export a legacy DB in one read-only snapshot. Run on the Docker host.
Usage: python3 backend/scripts/export_legacy_core.py --environment staging|prod --output /protected/snapshot.json
Never writes to the source DB; the output contains password hashes and private history.
"""

import argparse
import json
import os
import subprocess

DEFAULT_CONTAINERS = {
    "staging": "langear-staging-dev-postgres",
    "prod": "langear-prod-postgres",
}
OTHER_ENVIRONMENT = {"staging": "prod", "prod": "staging"}

TABLES = [
    "users",
    "decks",
    "cards",
    "user_card_srs",
    "user_card_fsrs",
    "review_log",
    "fsrs_review_log",
    "user_settings",
    "settings",
    "user_decks",
    "user_deck_cards",
    "invitation_codes",
]


def container_name(environment, override=None):
    """Resolve the source container without allowing an accidental cross-environment read."""
    name = override or DEFAULT_CONTAINERS[environment]
    other = OTHER_ENVIRONMENT[environment]
    if environment not in name or other in name:
        raise ValueError(
            f"{environment} export requires a {environment} container, got {name!r}"
        )
    return name


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--environment", choices=tuple(DEFAULT_CONTAINERS), default="staging")
    parser.add_argument("--container")
    args = parser.parse_args()
    try:
        container = container_name(args.environment, args.container)
    except ValueError as error:
        parser.error(str(error))
    pairs = ["'revision', (SELECT to_jsonb(version_num) FROM alembic_version)"]
    pairs += [
        f"'{table}', COALESCE((SELECT jsonb_agg(to_jsonb(t)) FROM {table} t), '[]'::jsonb)"
        for table in TABLES
    ]
    sql = (
        "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY; SELECT jsonb_build_object("
        + ",".join(pairs)
        + "); COMMIT;"
    )
    result = subprocess.check_output(
        [
            "docker",
            "exec",
            container,
            "sh",
            "-c",
            'exec psql -X -qAt -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "$1"',
            "sh",
            sql,
        ]
    )
    data = json.loads(result)
    # Canonical row order makes later exports comparable.
    for table in TABLES:
        data[table].sort(key=lambda row: json.dumps(row, sort_keys=True))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        json.dump(data, stream, sort_keys=True)
    print(json.dumps({table: len(data[table]) for table in TABLES}))


if __name__ == "__main__":
    main()
