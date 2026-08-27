"""Authentication router."""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.current_user import require_current_user_id
from app.services.auth_service import AuthError, AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])


class AuthRequest(BaseModel):
    """Username/password auth payload."""

    model_config = ConfigDict(extra="forbid")

    username: str
    password: str


class RegisterRequest(AuthRequest):
    """Registration payload."""

    invitation_code: str
    email: str | None = None


@router.post("/register")
def register(request: RegisterRequest, db: Session = Depends(get_db)):
    """Register a user account."""
    request_id = str(uuid.uuid4())
    try:
        data = AuthService(db).register(
            username=request.username,
            password=request.password,
            invitation_code=request.invitation_code,
            email=request.email,
        )
        return {
            "request_id": request_id,
            "data": data,
        }
    except AuthError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "AUTH_REGISTER_FAILED",
                    "message": str(exc),
                },
            },
        )


@router.post("/login")
def login(request: AuthRequest, db: Session = Depends(get_db)):
    """Log in with username and password."""
    request_id = str(uuid.uuid4())
    try:
        data = AuthService(db).login(request.username, request.password)
        return {
            "request_id": request_id,
            "data": data,
        }
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "AUTH_LOGIN_FAILED",
                    "message": str(exc),
                },
            },
        )


@router.get("/me")
def get_me(
    db: Session = Depends(get_db),
    user_id: int = Depends(require_current_user_id),
):
    """Return the authenticated user."""
    request_id = str(uuid.uuid4())
    try:
        user = AuthService(db).get_user_payload(user_id)
        return {
            "request_id": request_id,
            "data": user,
        }
    except AuthError as exc:
        raise HTTPException(
            status_code=401,
            detail={
                "request_id": request_id,
                "error": {
                    "code": "AUTH_USER_NOT_FOUND",
                    "message": str(exc),
                },
            },
        )
