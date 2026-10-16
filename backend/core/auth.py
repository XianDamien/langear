"""Opaque server sessions, Argon2id and CSRF for every cookie-auth write."""

import hashlib
import hmac
import secrets
from urllib.parse import urlsplit
from datetime import timedelta
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from sqlalchemy import case, delete, select
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
        "user": {"id": user.id, "email": user.email},
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
    user = User(email=body.email, password_hash=HASHER.hash(body.password))
    db.add(user)
    db.flush()
    collection = Collection(owner_user_id=user.id, timezone=body.timezone)
    db.add(collection)
    db.flush()
    db.add(Deck(collection_id=collection.id, name="Default"))
    db.flush()
    return open_session(db, user, request, response)


def login(db, body, request, response):
    require_origin(request)
    rate_limit(request, "login", body.email)
    user = db.scalar(select(User).where(User.email == body.email))
    try:
        HASHER.verify(user.password_hash if user else DUMMY_HASH, body.password)
        valid = user is not None and not user.disabled
    except (VerificationError, InvalidHashError):
        valid = False
    if not valid:
        raise DomainError(401, "INVALID_CREDENTIALS", "Invalid email or password.")
    if HASHER.check_needs_rehash(user.password_hash):
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
