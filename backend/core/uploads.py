"""Owned, single-use OSS audio upload grants; recordings reuse the browser recorder."""
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field
from uuid6 import uuid7

from core import auth
from core.config import get_settings
from core.content import ContentService
from core.db import get_db
from core.errors import DomainError
from core.models import Collection, MediaAsset
from core.schemas import Body

router = APIRouter(prefix="/api/v1/media-assets")
MAX_AUDIO_BYTES = 25 * 1024 * 1024
Identity = Annotated[Collection, Depends(auth.identity)]


class AudioUpload(Body):
    content_type: Literal["audio/webm"]
    size_bytes: int = Field(gt=0, le=MAX_AUDIO_BYTES, strict=True)


def bucket():
    settings = get_settings()
    if not all((settings.oss_access_key_id, settings.oss_access_key_secret, settings.oss_endpoint, settings.oss_bucket_name)):
        raise DomainError(503, "MEDIA_UNAVAILABLE", "Audio storage is temporarily unavailable.")
    import oss2
    return oss2.Bucket(
        oss2.Auth(settings.oss_access_key_id.get_secret_value(), settings.oss_access_key_secret.get_secret_value()),
        "https://" + settings.oss_endpoint.removeprefix("https://").removeprefix("http://"),
        settings.oss_bucket_name,
    )


def upload_grant(asset):
    headers = {"Content-Type": asset.content_type, "x-oss-forbid-overwrite": "true"}
    try:
        url = bucket().sign_url("PUT", asset.object_key, 900, headers=headers)
    except DomainError:
        raise
    except Exception:
        raise DomainError(503, "MEDIA_UNAVAILABLE", "Audio storage is temporarily unavailable.") from None
    return {"media_asset_id": asset.id, "upload_url": url, "headers": headers, "expires_in": 900}


def verify_audio(asset):
    try:
        storage = bucket()
        head = storage.head_object(asset.object_key)
        if int(head.content_length) != asset.size_bytes or head.content_type.split(";", 1)[0] != asset.content_type:
            raise DomainError(422, "MEDIA_UPLOAD_INVALID", "Uploaded audio does not match the grant.")
        # The existing recorder produces WebM, whose EBML header starts with this magic.
        if storage.get_object(asset.object_key, byte_range=(0, 3)).read() != b"\x1a\x45\xdf\xa3":
            raise DomainError(422, "MEDIA_UPLOAD_INVALID", "Expected a WebM recording.")
    except DomainError:
        raise
    except Exception:
        raise DomainError(409, "MEDIA_NOT_UPLOADED", "Upload the audio before confirming it.") from None


@router.post("/audio-uploads", status_code=201)
def create_upload(body: AudioUpload, collection: Identity, db=Depends(get_db, scope="function")):
    service = ContentService(db, collection)
    service.repo.lock()
    asset = MediaAsset(
        id=uuid7(), collection_id=collection.id, kind="audio", scope="private", lifecycle="temporary",
        object_key=f"{get_settings().upload_prefix.strip('/')}/{collection.id}/{uuid7()}.webm",
        content_type=body.content_type, size_bytes=body.size_bytes,
    )
    db.add(asset)
    db.flush()
    return upload_grant(asset)


@router.post("/{asset_id}/confirm-upload")
def confirm_upload(asset_id: UUID, collection: Identity, db=Depends(get_db, scope="function")):
    service = ContentService(db, collection)
    service.repo.lock()
    asset = service.repo.get(MediaAsset, asset_id)
    if asset.scope != "private" or asset.kind != "audio" or asset.lifecycle != "temporary" or asset.size_bytes is None:
        raise DomainError(409, "MEDIA_ALREADY_CLAIMED", "This upload cannot be confirmed.")
    if asset.uploaded_at is None:
        verify_audio(asset)
        asset.uploaded_at = datetime.now(UTC)
        db.flush()
    return {"media_asset_id": asset.id, "uploaded": True}
