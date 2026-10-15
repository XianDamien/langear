#!/usr/bin/env bash
# Run from backend/ with the test dependencies on PATH. Inherit no app credentials.
set -euo pipefail
exec env -i PATH="$PATH" PYTHONPATH="$PWD" \
  LANG=C.UTF-8 DATABASE_URL=sqlite:///:memory: \
  AUTH_TOKEN_SECRET=isolated-test-secret \
  GEMINI_API_KEY=test-key GEMINI_MODEL_ID=gemini-test-model \
  DASHSCOPE_API_KEY=test-key \
  OSS_ACCESS_KEY_ID=test-key OSS_ACCESS_KEY_SECRET=test-key \
  OSS_BUCKET_NAME=test-bucket OSS_ENDPOINT=oss-cn-test.aliyuncs.com \
  OSS_RECORDINGS_PREFIX=recordings \
  python -m pytest "$@"
