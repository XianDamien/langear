import logging

from app.logging_config import BeijingFormatter, setup_logging


def test_beijing_formatter_uses_asia_shanghai_offset():
    formatter = BeijingFormatter(datefmt="%Y-%m-%d %H:%M:%S %z")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    record.created = 0

    assert formatter.formatTime(record, formatter.datefmt) == "1970-01-01 08:00:00 +0800"


def test_setup_logging_configures_uvicorn_access_with_beijing_formatter():
    setup_logging()

    uvicorn_access_logger = logging.getLogger("uvicorn.access")

    assert uvicorn_access_logger.handlers
    assert isinstance(uvicorn_access_logger.handlers[0].formatter, BeijingFormatter)


def test_uvicorn_access_formatter_supports_uvicorn_message_shape():
    formatter = BeijingFormatter(fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    record = logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("172.18.0.1:52288", "GET", "/health", "1.1", 200),
        exc_info=None,
    )
    record.created = 0

    formatted = formatter.format(record)

    assert "1970-01-01 08:00:00 +0800" in formatted
    assert '172.18.0.1:52288 - "GET /health HTTP/1.1" 200' in formatted
