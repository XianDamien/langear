"""Current-user dependencies."""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.services.auth_service import AuthError, decode_access_token

bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    """Return the current user id.

    Requests with a Bearer token use the authenticated user. Missing tokens
    still fall back to the MVP default user during the migration window.
    """
    if credentials is None:
        return 1

    try:
        return decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


def require_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> int:
    """Require and decode an authenticated user id."""
    if credentials is None:
        raise HTTPException(status_code=401, detail="Missing authentication token")

    try:
        return decode_access_token(credentials.credentials)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc))
