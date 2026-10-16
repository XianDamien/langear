"""LAN-30 API entry point. Start with uvicorn core.main:app."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
from uuid6 import uuid7
from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import delete, or_, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException
from core import auth, schemas
from core.config import get_settings
from core.content import ContentService
from core.db import get_db, get_engine
from core.errors import DomainError, missing
from core.models import (
    Card,
    Collection,
    Deck,
    LoginSession,
    MediaAsset,
    Note,
    NoteType,
    User,
)

ROOT = Path(__file__).resolve().parents[1]


def expected_revision():
    config = Config(str(ROOT / "alembic-core.ini"))
    config.set_main_option("script_location", str(ROOT / "core_migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


@asynccontextmanager
async def lifespan(app):
    # Fail closed; migrations/seeding are explicit jobs, never web startup work.
    with get_engine().connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        if revision != expected_revision():
            raise RuntimeError(
                "Core schema revision mismatch; run the explicit core migration job."
            )
    yield


app = FastAPI(title="LanGear Collection API", version="3.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-CSRF-Token", "X-Request-ID", "Authorization"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def request_id(request, call_next):
    request.state.request_id = str(uuid7())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    response.headers["Cache-Control"] = "no-store"
    return response


def error_response(request, status, code, message, details=None):
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": getattr(request.state, "request_id", str(uuid7())),
            }
        },
    )


@app.exception_handler(DomainError)
async def domain_error(request, exc):
    return error_response(request, exc.status, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # Do not echo passwords, raw inputs or media credentials through Pydantic errors.
    errors = [
        {"location": list(item["loc"]), "type": item["type"], "message": item["msg"]}
        for item in exc.errors()
    ]
    status = (
        400 if any(item["type"] == "json_invalid" for item in exc.errors()) else 422
    )
    return error_response(
        request,
        status,
        "VALIDATION_ERROR",
        "Request validation failed.",
        {"errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return error_response(
        request,
        exc.status_code,
        "NOT_FOUND" if exc.status_code == 404 else "HTTP_ERROR",
        "Request could not be handled.",
    )


@app.exception_handler(IntegrityError)
async def integrity_error(request, exc):
    return error_response(
        request,
        409,
        "RESOURCE_CONFLICT",
        "A uniqueness or ownership constraint was violated.",
    )


@app.exception_handler(OperationalError)
async def unavailable(request, exc):
    return error_response(
        request, 503, "DATABASE_UNAVAILABLE", "The database is temporarily unavailable."
    )


@app.exception_handler(Exception)
async def internal_error(request, exc):
    logging.getLogger(__name__).error(
        "Unhandled error request_id=%s type=%s",
        getattr(request.state, "request_id", "unknown"),
        type(exc).__name__,
    )
    return error_response(
        request, 500, "INTERNAL_ERROR", "An unexpected server error occurred."
    )


@app.get("/health")
def health():
    return {"status": "healthy", "service": "collection-core"}


@app.get("/ready")
def ready(db=Depends(get_db, scope="function")):
    revision = db.scalar(text("SELECT version_num FROM alembic_version"))
    if revision != expected_revision():
        raise DomainError(503, "SCHEMA_MISMATCH", "Database schema is not ready.")
    return {"status": "ready", "schema_revision": revision}


@app.post("/api/v1/auth/register", status_code=201)
def register(
    body: schemas.Register,
    request: Request,
    response: Response,
    db=Depends(get_db, scope="function"),
):
    return auth.register(db, body, request, response)


@app.post("/api/v1/auth/legacy")
def legacy_login(
    request: Request, response: Response, db=Depends(get_db, scope="function")
):
    return auth.legacy_login(db, request, response)


@app.post("/api/v1/auth/login")
def login(
    body: schemas.Login,
    request: Request,
    response: Response,
    db=Depends(get_db, scope="function"),
):
    return auth.login(db, body, request, response)


@app.get("/api/v1/auth/me")
def me(
    request: Request,
    collection=Depends(auth.identity),
    db=Depends(get_db, scope="function"),
):
    return auth.public_identity(db.get(User, request.state.user_id), collection)


@app.post("/api/v1/auth/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    collection=Depends(auth.identity),
    db=Depends(get_db, scope="function"),
):
    db.execute(delete(LoginSession).where(LoginSession.id == request.state.session_id))
    response.delete_cookie(
        auth.COOKIE,
        path="/api/v1",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


@app.post("/api/v1/auth/password", status_code=204)
def password(
    body: schemas.PasswordChange,
    request: Request,
    response: Response,
    collection=Depends(auth.identity),
    db=Depends(get_db, scope="function"),
):
    user = db.get(User, request.state.user_id)
    auth.rate_limit(request, "password", user.email)
    try:
        auth.HASHER.verify(user.password_hash, body.current_password)
    except (auth.VerificationError, auth.InvalidHashError):
        raise DomainError(401, "INVALID_CREDENTIALS", "Current password is invalid.")
    user.password_hash = auth.HASHER.hash(body.new_password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    response.delete_cookie(
        auth.COOKIE,
        path="/api/v1",
        secure=get_settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )


@app.get("/api/v1/auth/csrf")
def csrf(
    request: Request,
    collection=Depends(auth.identity),
    db=Depends(get_db, scope="function"),
):
    auth.require_origin(request)
    value = auth.secrets.token_urlsafe(32)
    db.get(LoginSession, request.state.session_id).csrf_hash = auth.digest(value)
    return {"csrf_token": value}


def content(collection=Depends(auth.identity), db=Depends(get_db, scope="function")):
    return ContentService(db, collection)


@app.get("/api/v1/collection")
def collection_info(service=Depends(content)):
    collection = service.collection
    return {
        "id": collection.id,
        "kind": collection.kind,
        "timezone": collection.timezone,
        "scheduling_config": collection.scheduling_config,
    }


@app.get("/api/v1/library")
def library_info(service=Depends(content)):
    library = service.db.scalar(select(Collection).where(Collection.kind == "library"))
    return {"id": library.id, "kind": library.kind, "read_only": True}


@app.get("/api/v1/note-types")
def note_types(service=Depends(content)):
    return {
        "note_types": [
            {
                "id": nt.id,
                "key": nt.key,
                "display_name": nt.display_name,
                "read_only": True,
                "fields": [
                    {"key": f.key, "ord": f.ord, "kind": f.kind, "required": f.required}
                    for f in service.fields_for(nt.id)
                ],
                "card_templates": [
                    {
                        "id": t.id,
                        "key": t.key,
                        "ord": t.ord,
                        "required_fields": t.required_fields,
                        "q_format": t.q_format,
                        "a_format": t.a_format,
                        "input_type": t.input_type,
                    }
                    for t in service.templates_for(nt.id)
                ],
            }
            for nt in service.db.scalars(select(NoteType).order_by(NoteType.key))
        ]
    }


@app.get("/api/v1/decks")
def decks(
    service=Depends(content),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = service.db.scalars(
        select(Deck)
        .where(Deck.collection_id == service.collection.id)
        .order_by(Deck.id)
        .limit(limit)
        .offset(offset)
    )
    return {"decks": [service.deck_data(row) for row in rows]}


@app.post("/api/v1/decks", status_code=201)
def create_deck(body: schemas.DeckCreate, service=Depends(content)):
    return service.create_deck(body)


@app.get("/api/v1/decks/{deck_id}")
def get_deck(deck_id: UUID, service=Depends(content)):
    return service.deck_data(service.repo.get(Deck, deck_id))


@app.put("/api/v1/decks/{deck_id}")
def update_deck(deck_id: UUID, body: schemas.DeckUpdate, service=Depends(content)):
    return service.update_deck(deck_id, body)


@app.get("/api/v1/notes")
def notes(
    service=Depends(content),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = service.db.scalars(
        select(Note)
        .where(Note.collection_id == service.collection.id)
        .order_by(Note.id)
        .limit(limit)
        .offset(offset)
    )
    return {"notes": [service.note_data(row) for row in rows]}


@app.post("/api/v1/notes", status_code=201)
def create_note(body: schemas.NoteCreate, service=Depends(content)):
    return service.create_note(body)


@app.get("/api/v1/notes/{note_id}")
def get_note(note_id: UUID, service=Depends(content)):
    return service.note_data(service.repo.get(Note, note_id))


@app.put("/api/v1/notes/{note_id}")
def update_note(note_id: UUID, body: schemas.NoteUpdate, service=Depends(content)):
    return service.edit_note(note_id, body)


@app.post("/api/v1/notes/{note_id}/generate-cards")
def generate_cards(note_id: UUID, body: schemas.Generate, service=Depends(content)):
    return service.generate_missing(note_id, body)


@app.post("/api/v1/notes/{note_id}/change-type/preview")
def preview_type(note_id: UUID, body: schemas.TypePreview, service=Depends(content)):
    return service.type_preview(note_id, body.target_note_type_key)


@app.post("/api/v1/notes/{note_id}/change-type")
def change_type(note_id: UUID, body: schemas.TypeChange, service=Depends(content)):
    return service.change_type(note_id, body)


@app.get("/api/v1/cards")
def cards(
    deck_id: UUID | None = None,
    exclude_imported: bool = False,
    service=Depends(content),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = select(Card).where(Card.collection_id == service.collection.id)
    if exclude_imported:
        query = query.join(Note, Card.note_id == Note.id).where(
            ~Note.guid.startswith("legacy:")
        )
    if deck_id:
        service.repo.get(Deck, deck_id)
        query = query.where(Card.deck_id == deck_id)
    return {
        "cards": [
            service.render(card)
            for card in service.db.scalars(
                query.order_by(Card.id).limit(limit).offset(offset)
            )
        ]
    }


@app.get("/api/v1/cards/{card_id}")
def get_card(card_id: UUID, service=Depends(content)):
    return service.render(service.repo.get(Card, card_id))


@app.put("/api/v1/cards/{card_id}/deck")
def move_card(card_id: UUID, body: schemas.Generate, service=Depends(content)):
    return service.move_card(card_id, body.deck_id)


@app.post("/api/v1/{resource_type}/{resource_id}/delete/preview")
def preview_delete(resource_type: str, resource_id: UUID, service=Depends(content)):
    kind = {"notes": "note", "cards": "card", "decks": "deck"}.get(resource_type)
    if kind is None:
        missing()
    return service.deletion_preview(kind, resource_id)


@app.post("/api/v1/{resource_type}/{resource_id}/delete")
def execute_delete(
    resource_type: str,
    resource_id: UUID,
    body: schemas.Confirm,
    service=Depends(content),
):
    kind = {"notes": "note", "cards": "card", "decks": "deck"}.get(resource_type)
    if kind is None:
        missing()
    return service.delete_resource(kind, resource_id, body.confirmation_token)


@app.get("/api/v1/media-assets")
def media_assets(
    service=Depends(content),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    rows = service.db.scalars(
        select(MediaAsset)
        .where(
            MediaAsset.lifecycle == "ready",
            or_(
                MediaAsset.collection_id == service.collection.id,
                MediaAsset.scope == "library_shared",
            ),
        )
        .order_by(MediaAsset.id)
        .limit(limit)
        .offset(offset)
    )
    return {
        "media_assets": [
            {
                "id": asset.id,
                "kind": asset.kind,
                "name": asset.object_key.rsplit("/", 1)[-1],
            }
            for asset in rows
        ]
    }


@app.put("/api/v1/decks/{deck_id}/membership")
def set_deck_membership(deck_id: UUID, body: schemas.DeckMembership, service=Depends(content)):
    service.repo.lock()
    deck = service.repo.standard_deck(deck_id)
    deck.in_my_courses = body.joined
    service.db.flush()
    return service.deck_data(deck)


@app.get("/api/v1/media-assets/{asset_id}/url")
def media_asset_url(asset_id: UUID, service=Depends(content)):
    asset = service.db.scalar(select(MediaAsset).where(
        MediaAsset.id == asset_id,
        MediaAsset.lifecycle == "ready",
        or_(MediaAsset.collection_id == service.collection.id, MediaAsset.scope == "library_shared"),
    ))
    if asset is None:
        missing()
    from core.media import sign_media
    return {"url": sign_media(asset.object_key), "kind": asset.kind, "expires_in": 900}
