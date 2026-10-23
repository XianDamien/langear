import os
import time
import pytest
from datetime import timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
from core import processing
from core.config import get_settings
from core.models import ProcessingOutbox, utcnow
from core_tests.test_review import make_note, queue, next_card, flip


def test_worker_probe_checks_heartbeat_liveness_and_database(engine, monkeypatch, tmp_path):
    marker = tmp_path / "heartbeat"
    monkeypatch.setattr(processing, "HEARTBEAT", marker)
    with pytest.raises(FileNotFoundError):
        processing.healthcheck()
    processing.heartbeat()
    processing.healthcheck()
    marker.write_text(f"{os.getpid()} {time.time() - processing.HEARTBEAT_MAX_AGE - 1}")
    with pytest.raises(RuntimeError, match="expired"):
        processing.healthcheck()


def test_worker_health_detects_old_pending_jobs_and_recovers(client, account, engine, monkeypatch, tmp_path):
    monkeypatch.setattr(processing, "HEARTBEAT", tmp_path / "heartbeat")
    processing.heartbeat()
    make_note(client, account, {"english": "Hello", "chinese": "你好"}, "sentence_translation")
    q = queue(client, account)
    flip(client, q, next_card(client, q), {"type": "text", "text": "Hi"})
    processing.healthcheck()
    with Session(engine) as db, db.begin():
        job = db.scalar(select(ProcessingOutbox))
        job.created_at = utcnow() - timedelta(seconds=get_settings().review_backlog_max_age_seconds + 1)
    with pytest.raises(RuntimeError, match="backlog overdue: count=1"):
        processing.healthcheck()
    with Session(engine) as db, db.begin():
        db.scalar(select(ProcessingOutbox)).status = "succeeded"
    processing.healthcheck()
