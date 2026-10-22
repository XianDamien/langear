"""Multiple outbox consumers share pending jobs without double-processing."""

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.models import ProcessingOutbox
from core_tests.test_review import flip, make_note, next_card, queue, rate
from core_tests.test_review_migration import recording

BACKEND = Path(__file__).resolve().parents[1]


def test_multiple_workers_share_the_outbox_without_duplicates(
    client, account, engine, tmp_path
):
    sentences = [f"Worker concurrency sentence {index}" for index in range(6)]
    for sentence in sentences:
        make_note(
            client,
            account,
            {
                "english": sentence,
                "chinese": "并发测试",
                "reference_audio": recording(engine, account, ready=True),
            },
            "sentence_retelling",
        )

    review_queue = queue(client, account)
    for _ in sentences:
        current = next_card(client, review_queue)
        flipped = flip(
            client,
            review_queue,
            current,
            {"type": "audio", "temporary_media_asset_id": recording(engine, account)},
        )
        assert flipped.status_code == 200, flipped.text
        assert rate(client, review_queue, flipped.json(), "good").status_code == 200

    worker_log = tmp_path / "workers.log"
    env = os.environ.copy()
    env["WORKER_TEST_LOG"] = str(worker_log)
    env["PYTHONPATH"] = str(BACKEND) + os.pathsep + env.get("PYTHONPATH", "")
    worker_script = BACKEND / "core_tests" / "worker_consumer.py"
    workers = [
        subprocess.Popen(
            [sys.executable, str(worker_script)],
            cwd=BACKEND,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for _ in range(3)
    ]
    for worker in workers:
        _, error = worker.communicate(timeout=60)
        assert worker.returncode == 0, error.decode()

    rows = [line.split("\t") for line in worker_log.read_text().splitlines() if line]
    assert sorted(row[3] for row in rows) == sorted(sentences)
    assert len({row[0] for row in rows}) >= 2

    intervals = sorted((float(row[1]), float(row[2])) for row in rows)
    assert any(
        following_start < current_end
        for (_, current_end), (following_start, _) in zip(intervals, intervals[1:])
    )

    with Session(engine) as db:
        jobs = list(
            db.scalars(select(ProcessingOutbox).where(ProcessingOutbox.kind == "ai"))
        )
        assert len(jobs) == len(sentences)
        assert all(job.status == "succeeded" for job in jobs)
