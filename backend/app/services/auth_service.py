"""Authentication helpers and service layer."""

import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy.orm import Session

from app.config import settings
from app.models.invitation_code import InvitationCode
from app.models.user import User
from app.utils.timezone import storage_now

TOKEN_TTL_SECONDS = 60 * 60 * 24 * 7
PASSWORD_ITERATIONS = 210_000


class AuthError(ValueError):
    """Raised for invalid auth operations."""


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256."""
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, stored_hash: str | None) -> bool:
    """Verify a plaintext password against a stored password hash."""
    if not stored_hash:
        return False

    try:
        algorithm, iterations, salt, digest = stored_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        computed = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            _b64url_decode(salt),
            int(iterations),
        )
        return hmac.compare_digest(_b64url_encode(computed), digest)
    except (ValueError, TypeError):
        return False


def _auth_secret() -> bytes:
    """Return the HMAC secret used for local auth tokens."""
    raw_secret = getattr(settings, "auth_token_secret", None) or settings.gemini_api_key
    return raw_secret.encode("utf-8")


def create_access_token(user_id: int) -> str:
    """Create a signed access token for a user."""
    now = storage_now()
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=TOKEN_TTL_SECONDS)).timestamp()),
        "nonce": secrets.token_urlsafe(12),
    }
    payload_segment = _b64url_encode(
        json.dumps(payload, separators=(",", ":")).encode("utf-8")
    )
    signature = hmac.new(_auth_secret(), payload_segment.encode("ascii"), hashlib.sha256).digest()
    return f"{payload_segment}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> int:
    """Decode and validate a signed access token."""
    try:
        payload_segment, signature_segment = token.split(".", 1)
        expected = hmac.new(
            _auth_secret(),
            payload_segment.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(_b64url_encode(expected), signature_segment):
            raise AuthError("Invalid token signature")

        payload = json.loads(_b64url_decode(payload_segment))
        if int(payload["exp"]) < int(storage_now().timestamp()):
            raise AuthError("Token has expired")
        return int(payload["sub"])
    except (KeyError, ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Invalid token") from exc


class AuthService:
    """Service for account registration and login."""

    def __init__(self, db: Session):
        """Initialize service with database session."""
        self.db = db

    def register(
        self,
        username: str,
        password: str,
        invitation_code: str,
        email: str | None = None,
    ) -> dict[str, Any]:
        """Create a user account and return an access token."""
        username = self._normalize_username(username)
        self._validate_password(password)
        invitation = self._get_usable_invitation_code(invitation_code)

        existing = self.db.query(User).filter(User.username == username).first()
        if existing is not None and existing.password_hash:
            raise AuthError("Username is already registered")

        if email:
            email = email.strip().lower()
            email_owner = self.db.query(User).filter(User.email == email).first()
            if email_owner is not None and email_owner is not existing:
                raise AuthError("Email is already registered")

        user = existing or User(username=username)
        user.email = email
        user.email_verified_at = None
        user.password_hash = hash_password(password)
        user.invitation_code_id = invitation.id
        invitation.used_count += 1
        self.db.add(user)
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(user)
        return self._auth_payload(user)

    def login(self, username: str, password: str) -> dict[str, Any]:
        """Validate credentials and return an access token."""
        username = self._normalize_username(username)
        user = self.db.query(User).filter(User.username == username).first()
        if user is None or not verify_password(password, user.password_hash):
            raise AuthError("Invalid username or password")
        return self._auth_payload(user)

    def get_user_payload(self, user_id: int) -> dict[str, Any]:
        """Return the public current-user payload."""
        user = self.db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise AuthError("User does not exist")
        return self._user_payload(user)

    def _auth_payload(self, user: User) -> dict[str, Any]:
        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
            "user": self._user_payload(user),
        }

    @staticmethod
    def _user_payload(user: User) -> dict[str, Any]:
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "email_verified": user.email_verified_at is not None,
            "email_verified_at": (
                user.email_verified_at.isoformat() if user.email_verified_at else None
            ),
        }

    @staticmethod
    def _normalize_username(username: str) -> str:
        username = username.strip()
        if len(username) < 3 or len(username) > 50:
            raise AuthError("Username must be 3 to 50 characters")
        return username

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters")

    def _get_usable_invitation_code(self, code: str) -> InvitationCode:
        code = code.strip()
        if not code:
            raise AuthError("Invitation code is required")

        invitation = (
            self.db.query(InvitationCode)
            .filter(InvitationCode.code == code)
            .with_for_update()
            .first()
        )
        now = storage_now()
        if invitation is None:
            raise AuthError("Invitation code is invalid")
        if invitation.disabled_at is not None:
            raise AuthError("Invitation code is disabled")
        if invitation.expires_at is not None and invitation.expires_at < now:
            raise AuthError("Invitation code has expired")
        if invitation.used_count >= invitation.max_uses:
            raise AuthError("Invitation code has been used")
        return invitation
