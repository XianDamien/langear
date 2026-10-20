FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_HTTP_TIMEOUT=120 \
    UV_HTTP_RETRIES=3

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY core ./core
COPY core_migrations ./core_migrations
COPY alembic-core.ini ./

RUN uv sync --locked --no-dev

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/core /app/core
COPY --from=builder /app/core_migrations /app/core_migrations
COPY --from=builder /app/alembic-core.ini /app/alembic-core.ini

RUN mkdir -p /app/data

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import json, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3); payload = json.load(response); raise SystemExit(0 if payload.get('status') == 'healthy' else 1)"

CMD ["uvicorn", "core.core_only:app", "--host", "0.0.0.0", "--port", "8000"]
