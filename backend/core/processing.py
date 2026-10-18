"""Durable Review outbox consumer. Run alongside the API: python -m core.processing.

A PostgreSQL row lock owns each job until its result commits. Process death rolls
back the job so the next worker can recover it without a broker or a Celery task.
Provider requests may repeat after a crash; committed results are consumed once.
"""
import logging
from threading import Event
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from core.db import get_engine
from core.media import sign_media
from core.models import Attempt, MediaAsset, ProcessingOutbox

logger = logging.getLogger(__name__)


def transcribe(url):
    from app.adapters.asr_adapter import ASRAdapter
    return ASRAdapter().transcribe(url)


def feedback_provider():
    from app.adapters.ai_feedback_adapter import create_ai_feedback_provider
    return create_ai_feedback_provider()


def audio_url(db, asset_id, collection_id):
    asset = db.get(MediaAsset, UUID(str(asset_id))) if asset_id else None
    if (asset is None or asset.kind != "audio" or asset.lifecycle != "ready"
            or (asset.scope != "library_shared" and asset.collection_id != collection_id)):
        raise ValueError("Recording is unavailable")
    return sign_media(asset.object_key)


def process_one(engine=None):
    with Session(engine or get_engine()) as db, db.begin():
        job = db.scalar(select(ProcessingOutbox).join(Attempt, Attempt.id == ProcessingOutbox.attempt_id).where(
            ProcessingOutbox.status == "pending",
            or_(ProcessingOutbox.kind == "asr", Attempt.asr_status.notin_(["pending", "processing"])),
        ).order_by(ProcessingOutbox.created_at, ProcessingOutbox.id).with_for_update(skip_locked=True, of=ProcessingOutbox).limit(1))
        if job is None:
            return False
        attempt = db.get(Attempt, job.attempt_id)
        field = job.kind + "_status"
        if getattr(attempt, field) not in ("pending", "processing"):
            job.status = "succeeded"
            return True
        try:
            # The savepoint also rolls back partial results on provider errors.
            with db.begin_nested():
                if job.kind == "asr":
                    result = transcribe(audio_url(db, attempt.media_asset_id, attempt.collection_id))
                    if not isinstance(result.get("text"), str) or not result["text"].strip():
                        raise ValueError("No transcript returned")
                    attempt.asr_result = result
                else:
                    provider = feedback_provider()
                    if attempt.input_type == "text":
                        result = provider.generate_translation_feedback(
                            attempt.note_snapshot.get("chinese", ""),
                            attempt.answer_snapshot.get("english", attempt.note_snapshot.get("english", "")),
                            attempt.input_snapshot["text"],
                        )
                    else:
                        result = provider.generate_single_feedback(
                            front_text=attempt.note_snapshot["english"],
                            user_audio_url=audio_url(db, attempt.media_asset_id, attempt.collection_id),
                            reference_audio_url=audio_url(db, attempt.note_snapshot.get("reference_audio"), attempt.collection_id),
                        )
                    # Retain the Qwen transcript; feedback must not rewrite input.
                    result.pop("transcription_text", None)
                    attempt.ai_feedback = result
                setattr(attempt, field, "succeeded")
                job.status = "succeeded"
        except Exception as exc:
            # Never persist provider exception bodies, signed URLs, or secrets.
            logger.warning("Review processing failed: job=%s kind=%s error=%s", job.id, job.kind, type(exc).__name__)
            setattr(attempt, field, "failed")
            job.status = "failed"
        return True


def run():
    import signal
    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    while not stop.is_set():
        try:
            if process_one():
                continue
        except Exception as exc:
            logger.warning("Review worker transaction failed: %s", type(exc).__name__)
        stop.wait(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
