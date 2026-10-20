#!/usr/bin/env bash
# Run only against an explicitly provisioned, disposable PostgreSQL database.
set -euo pipefail
: "${CORE_TEST_DATABASE_URL:?Set CORE_TEST_DATABASE_URL to a disposable lan30_test_* database}"
exec env -i PATH="$PATH" PYTHONPATH="$PWD" LANG=C.UTF-8 PGTZ=UTC TZ=UTC   CORE_TEST_DATABASE_URL="$CORE_TEST_DATABASE_URL"   python -m pytest core_tests "$@"
