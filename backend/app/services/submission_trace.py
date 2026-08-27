"""Shared logging helper for submission trace events."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any


def _json_default(value: Any) -> str:
    """Serialize non-JSON-native values for structured logs."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def log_submission_trace(
    logger: logging.Logger,
    stage: str,
    *,
    level: str = "info",
    **fields: Any,
) -> None:
    """Emit a structured submission trace log line."""
    payload = {
        "event": "submission_trace",
        "stage": stage,
        **{key: value for key, value in fields.items() if value is not None},
    }
    message = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=_json_default)
    getattr(logger, level)("submission_trace %s", message)
