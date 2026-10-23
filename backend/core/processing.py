"""Durable Review outbox consumer. Run alongside the API: python -m core.processing.

A PostgreSQL row lock owns each job until its result commits. Process death rolls
back the job so the next worker can recover it without a broker or a Celery task.
Provider requests may repeat after a crash; committed results are consumed once.
"""
import logging
import os
from pathlib import Path
import time
from datetime import timedelta
from threading import Event, Thread, local
from uuid import UUID

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from core.db import get_engine
from core.media import sign_media
from core.models import Attempt, MediaAsset, ProcessingOutbox, utcnow

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3
HEARTBEAT = Path("/tmp/langear-review-worker.heartbeat")
HEARTBEAT_MAX_AGE = 600
_providers = local()



def transcribe(url):
    from core.integrations.asr import transcribe as run
    return run(url)


def feedback_provider():
    from core.integrations.feedback import create_provider
    # Thread-local clients reuse connections without sharing SDK mutable state.
    if not hasattr(_providers, "provider"):
        _providers.provider = create_provider()
    return _providers.provider


def close_feedback_provider():
    provider = getattr(_providers, "provider", None)
    if provider is not None:
        del _providers.provider
        close = getattr(provider, "close", None)
        if close is not None:
            close()


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
            or_(ProcessingOutbox.next_attempt_at.is_(None), ProcessingOutbox.next_attempt_at <= utcnow()),
            or_(ProcessingOutbox.kind == "asr", Attempt.asr_status.notin_(["pending", "processing"])),
        ).order_by(ProcessingOutbox.created_at, ProcessingOutbox.id).with_for_update(skip_locked=True, of=ProcessingOutbox).limit(1))
        if job is None:
            return False
        attempt = db.get(Attempt, job.attempt_id)
        field = job.kind + "_status"
        if getattr(attempt, field) not in ("pending", "processing"):
            job.status = "succeeded"
            return True
        job.retry_count += 1
        started = time.monotonic()
        age = (utcnow() - job.created_at).total_seconds()
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
                job.next_attempt_at = None
        except Exception as exc:
            # Never persist provider exception bodies, signed URLs, or secrets.
            logger.warning(
                "Review processing failed: job=%s kind=%s error=%s reason=%s attempt=%s",
                job.id, job.kind, type(exc).__name__, getattr(exc, "reason", None), job.retry_count,
            )
            exhausted = job.retry_count >= MAX_ATTEMPTS
            setattr(attempt, field, "failed" if exhausted else "pending")
            job.status = "failed" if exhausted else "pending"
            job.next_attempt_at = None if exhausted else utcnow() + timedelta(seconds=5 * 2 ** (job.retry_count - 1))
        logger.info(
            "Review processing: job=%s kind=%s status=%s attempt=%s age_s=%.3f elapsed_s=%.3f",
            job.id, job.kind, job.status, job.retry_count, age, time.monotonic() - started,
        )
        return True


def retry_failed(db, collection, attempt_id):
    from core.errors import missing
    # Same lock order as workers: outbox, then Attempt. Repeated requests are a no-op.
    jobs = list(db.scalars(select(ProcessingOutbox).where(
        ProcessingOutbox.collection_id == collection.id, ProcessingOutbox.attempt_id == attempt_id,
    ).order_by(ProcessingOutbox.id).with_for_update()))
    attempt = db.scalar(select(Attempt).where(
        Attempt.collection_id == collection.id, Attempt.id == attempt_id,
    ).with_for_update())
    if attempt is None:
        missing()
    for job in jobs:
        field = job.kind + "_status"
        if job.status == "failed" and getattr(attempt, field) == "failed":
            job.status, job.retry_count, job.next_attempt_at = "pending", 0, None
            setattr(attempt, field, "pending")
    db.flush()


def heartbeat():
    HEARTBEAT.write_text(f"{os.getpid()} {time.time()}")


def healthcheck():
    pid, last = HEARTBEAT.read_text().split()
    os.kill(int(pid), 0)
    if not 0 <= time.time() - float(last) <= HEARTBEAT_MAX_AGE:
        raise RuntimeError("Worker heartbeat expired")
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
        from core.config import get_settings
        cutoff = utcnow() - timedelta(seconds=get_settings().review_backlog_max_age_seconds)
        stale = connection.scalar(select(func.count()).select_from(ProcessingOutbox).where(
            ProcessingOutbox.status == "pending", ProcessingOutbox.created_at < cutoff,
        ))
        if stale:
            raise RuntimeError(f"Review outbox backlog overdue: count={stale}")


def process_loop(stop):
    try:
        while not stop.is_set():
            try:
                if process_one():
                    continue
            except Exception as exc:
                logger.warning("Review worker transaction failed: %s", type(exc).__name__)
            stop.wait(1)
    finally:
        close_feedback_provider()


def heartbeat_loop(stop):
    while not stop.is_set():
        heartbeat()
        stop.wait(5)


def run():
    import signal
    from core.config import get_settings

    stop = Event()
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    concurrency = get_settings().review_worker_concurrency
    logger.info("Review worker started: concurrency=%s", concurrency)
    heartbeat_thread = Thread(
        target=heartbeat_loop, args=(stop,), name="review-heartbeat", daemon=True
    )
    heartbeat_thread.start()
    workers = [
        Thread(target=process_loop, args=(stop,), name=f"review-worker-{index}", daemon=True)
        for index in range(concurrency)
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    heartbeat_thread.join()


if __name__ == "__main__":
    import sys
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s [%(threadName)s] %(message)s",
    )
    if sys.argv[1:] == ["--healthcheck"]:
        try:
            healthcheck()
        except Exception as exc:
            # Only our own health errors carry safe diagnostic text.
            if isinstance(exc, RuntimeError):
                logger.error("Review worker unhealthy: %s", exc)
            raise SystemExit(1) from None
    else:
        run()
