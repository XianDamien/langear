"""Application logging configuration."""

from __future__ import annotations

import logging
import logging.config
from datetime import datetime
from zoneinfo import ZoneInfo


LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S %z"
DEFAULT_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
ACCESS_LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


class BeijingFormatter(logging.Formatter):
    """Formatter that renders timestamps in Beijing time."""

    def formatTime(self, record: logging.LogRecord, datefmt: str | None = None) -> str:
        dt = datetime.fromtimestamp(record.created, tz=BEIJING_TIMEZONE)
        if datefmt:
            return dt.strftime(datefmt)
        return dt.strftime(LOG_DATE_FORMAT)


def setup_logging() -> None:
    """Configure root and uvicorn loggers to use Beijing-time timestamps."""
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "()": "app.logging_config.BeijingFormatter",
                    "format": DEFAULT_LOG_FORMAT,
                    "datefmt": LOG_DATE_FORMAT,
                },
                "access": {
                    "()": "app.logging_config.BeijingFormatter",
                    "format": ACCESS_LOG_FORMAT,
                    "datefmt": LOG_DATE_FORMAT,
                },
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                    "stream": "ext://sys.stdout",
                },
                "access": {
                    "class": "logging.StreamHandler",
                    "formatter": "access",
                    "stream": "ext://sys.stdout",
                },
            },
            "root": {
                "level": "INFO",
                "handlers": ["default"],
            },
            "loggers": {
                "uvicorn": {
                    "level": "INFO",
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.error": {
                    "level": "INFO",
                    "handlers": ["default"],
                    "propagate": False,
                },
                "uvicorn.access": {
                    "level": "INFO",
                    "handlers": ["access"],
                    "propagate": False,
                },
            },
        }
    )
