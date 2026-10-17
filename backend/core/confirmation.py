"""Short-lived signed impact digests; no resource content is embedded in tokens."""

import base64
import hashlib
import hmac
import json
import time
from core.config import get_settings
from core.errors import DomainError


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def signature(payload):
    return hmac.new(
        get_settings().confirmation_secret.encode(), payload.encode(), hashlib.sha256
    ).hexdigest()


def issue(operation, collection_id, resource_id, impact):
    payload = {
        "op": operation,
        "collection": str(collection_id),
        "resource": str(resource_id),
        "impact": fingerprint(impact),
        "expires": int(time.time()) + get_settings().confirmation_seconds,
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(payload, separators=(",", ":")).encode()
    ).decode()
    return encoded + "." + signature(encoded)


def verify(
    token, operation, collection_id, resource_id, impact, code="DELETION_IMPACT_CHANGED"
):
    try:
        encoded, supplied = token.split(".")
        if not hmac.compare_digest(supplied, signature(encoded)):
            raise ValueError()
        payload = json.loads(base64.urlsafe_b64decode(encoded))
        if (
            payload["op"] != operation
            or payload["collection"] != str(collection_id)
            or payload["resource"] != str(resource_id)
            or payload["impact"] != fingerprint(impact)
            or payload["expires"] <= time.time()
        ):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise DomainError(
            409, code, "The preview is stale or invalid. Preview the operation again."
        )
