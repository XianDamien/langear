"""Test-only outbox consumer used to exercise multiple worker processes."""

import os
import time

from core import processing
from core.db import get_engine

LOG = os.environ["WORKER_TEST_LOG"]


class SlowProvider:
    def generate_single_feedback(self, front_text, **_):
        started = time.time()
        time.sleep(0.8)
        ended = time.time()
        with open(LOG, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\t{started:.6f}\t{ended:.6f}\t{front_text}\n")
        return {
            "pronunciation": "ok",
            "completeness": "ok",
            "fluency": "ok",
            "suggestions": [],
            "issues": [],
        }


processing.feedback_provider = lambda: SlowProvider()
processing.audio_url = lambda db, asset_id, collection_id: "https://oss.test/recording.webm"
processing.transcribe = lambda url: {"text": "Hello", "timestamps": []}

engine = get_engine()
while processing.process_one(engine):
    pass
