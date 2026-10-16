"""Opaque server sessions, Argon2id and CSRF for every cookie-auth write."""

import base64
import binascii
import hashlib
import hmac
import secrets
from urllib.parse import urlsplit
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import case, delete, select, or_
from sqlalchemy.dialects.postgresql import insert
from core.config import get_settings
from core.db import get_db, get_engine
from core.errors import DomainError
from core.models import AuthRateLimit, Collection, Deck, LoginSession, User, utcnow

COOKIE = "langear_core_session"
HASHER = PasswordHasher()
DUMMY_HASH = HASHER.hash(secrets.token_urlsafe(32))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def require_origin(request):
    origin = request.headers.get("origin")
    if not origin and request.method == "GET":
        referer = urlsplit(request.headers.get("referer", ""))
        origin = f"{referer.scheme}://{referer.netloc}"
    if origin not in get_settings().allowed_origins:
        raise DomainError(403, "ORIGIN_FORBIDDEN", "A trusted Origin is required.")


def rate_limit(request, operation, email):
    # Separate transaction: failed password checks must still consume the quota.
    # Shared PostgreSQL counters work across web workers and restarts.
    now = utcnow()
    window = now.replace(minute=now.minute - now.minute % 15, second=0, microsecond=0)
    identities = [
        "ip:" + (request.client.host if request.client else "unknown"),
        "email:" + email,
    ]
    exceeded = False
    with get_engine().begin() as connection:
        for identity in identities:
            key = digest(operation + ":" + identity)
            statement = insert(AuthRateLimit).values(
                key=key, window_start=window, count=1
            )
            statement = statement.on_conflict_do_update(
                index_elements=[AuthRateLimit.key],
                set_={
                    "window_start": window,
                    "count": case(
                        (AuthRateLimit.window_start == window, AuthRateLimit.count + 1),
                        else_=1,
                    ),
                },
            ).returning(AuthRateLimit.count)
            exceeded |= connection.scalar(statement) > get_settings().auth_limit
        connection.execute(
            delete(AuthRateLimit).where(
                AuthRateLimit.window_start < now - timedelta(days=1)
            )
        )
    if exceeded:
        raise DomainError(429, "RATE_LIMITED", "Too many authentication attempts.")


def public_identity(user, collection):
    return {
        "user": {"id": user.id, "email": user.email, "username": user.username},
        "collection": {
            "id": collection.id,
            "timezone": collection.timezone,
            "kind": collection.kind,
        },
    }


def open_session(db, user, request, response):
    old = request.cookies.get(COOKIE)
    if old:
        db.execute(delete(LoginSession).where(LoginSession.token_hash == digest(old)))
    token, csrf = secrets.token_urlsafe(48), secrets.token_urlsafe(32)
    settings = get_settings()
    db.add(
        LoginSession(
            user_id=user.id,
            token_hash=digest(token),
            csrf_hash=digest(csrf),
            expires_at=utcnow() + timedelta(seconds=settings.session_absolute_seconds),
        )
    )
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.session_absolute_seconds,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
    collection = db.scalar(
        select(Collection).where(Collection.owner_user_id == user.id)
    )
    return {**public_identity(user, collection), "csrf_token": csrf}


def register(db, body, request, response):
    require_origin(request)
    rate_limit(request, "register", body.email)
    if db.scalar(select(User.id).where(User.username == body.email)):
        raise DomainError(409, "CONFLICT", "This account identity already exists.")
    user = User(email=body.email, password_hash=HASHER.hash(body.password))
    db.add(user)
    db.flush()
    collection = Collection(owner_user_id=user.id, timezone=body.timezone)
    db.add(collection)
    db.flush()
    db.add(Deck(collection_id=collection.id, name="Default"))
    db.flush()
    return open_session(db, user, request, response)


def verify_password(stored_hash, password):
    """Read legacy hashes without importing legacy runtime/configuration."""
    try:
        if stored_hash.startswith("pbkdf2_sha256$"):
            _, rounds, salt, expected = stored_hash.split("$")
            iterations = int(rounds)
            if not 100000 <= iterations <= 1000000:
                return False
            decoded = base64.b64decode(
                salt + "=" * (-len(salt) % 4), altchars=b"-_", validate=True
            )
            if not 8 <= len(decoded) <= 128 or len(expected) != 43:
                return False
            actual = hashlib.pbkdf2_hmac(
                "sha256", password.encode(), decoded, iterations
            )
            return hmac.compare_digest(
                base64.urlsafe_b64encode(actual).rstrip(b"=").decode(), expected
            )
        return HASHER.verify(stored_hash, password)
    except (VerificationError, InvalidHashError, ValueError, binascii.Error):
        return False


def login(db, body, request, response):
    require_origin(request)
    rate_limit(request, "login", body.email)
    users = list(
        db.scalars(
            select(User).where(
                or_(User.email == body.email, User.username == body.email)
            )
        )
    )
    user = users[0] if len(users) == 1 else None
    valid = verify_password(user.password_hash if user else DUMMY_HASH, body.password)
    if not valid or user is None or user.disabled:
        raise DomainError(
            401, "INVALID_CREDENTIALS", "Invalid username/email or password."
        )
    if user.password_hash.startswith("pbkdf2_sha256$") or HASHER.check_needs_rehash(
        user.password_hash
    ):
        user.password_hash = HASHER.hash(body.password)
    return open_session(db, user, request, response)


def identity(request: Request, db=Depends(get_db, scope="function")):
    token = request.cookies.get(COOKIE)
    row = (
        db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(token)))
        if token
        else None
    )
    now = utcnow()
    if (
        row is None
        or row.expires_at <= now
        or row.last_seen_at + timedelta(seconds=get_settings().session_idle_seconds)
        <= now
    ):
        raise DomainError(401, "UNAUTHENTICATED", "Sign in to continue.")
    user = db.get(User, row.user_id)
    if user is None or user.disabled:
        raise DomainError(401, "UNAUTHENTICATED", "Sign in to continue.")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        require_origin(request)
        csrf = request.headers.get("x-csrf-token", "")
        if not hmac.compare_digest(row.csrf_hash, digest(csrf)):
            raise DomainError(403, "CSRF_INVALID", "CSRF token is invalid.")
    row.last_seen_at = now
    collection = db.scalar(
        select(Collection).where(Collection.owner_user_id == user.id)
    )
    request.state.session_id = row.id
    request.state.user_id = user.id
    return collection
