"""Count-only telemetry for retired SPA routes.

The payload intentionally excludes user identifiers, card content and query
strings. Hits are emitted as structured log lines so the seven-day zero-traffic
rule can be verified from the service logs without a new database table.
"""

import logging
import re

from fastapi import APIRouter, Request, Response

router = APIRouter(prefix="/api/v1/telemetry")
logger = logging.getLogger("core.telemetry")

ROUTES = {"Study", "Summary"}
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
SHA = re.compile(r"^(?:[0-9a-f]{40}|unknown)$")


@router.post("/legacy-route-hits", status_code=204)
async def legacy_route_hit(request: Request):
    try:
        body = await request.json()
    except (ValueError, TypeError):
        body = {}
    route = body.get("route") if isinstance(body, dict) else None
    date = body.get("date") if isinstance(body, dict) else None
    sha = body.get("release_sha") if isinstance(body, dict) else None
    logger.info(
        "legacy_route_hit route=%s date=%s release_sha=%s",
        route if route in ROUTES else "invalid",
        date if isinstance(date, str) and DATE.fullmatch(date) else "invalid",
        sha if isinstance(sha, str) and SHA.fullmatch(sha) else "invalid",
    )
    return Response(status_code=204)
