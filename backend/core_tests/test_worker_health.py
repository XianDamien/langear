import os
import time
import pytest
from core import processing


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
