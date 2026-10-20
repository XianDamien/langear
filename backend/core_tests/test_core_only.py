"""Core must run with the legacy `app` package physically absent.

A blocking import hook guards against a regression that reintroduces the
dependency: any attempt to import `app` or a submodule raises immediately.
"""

import builtins
import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]

ISOLATED = r"""
import sys

class BlockLegacy:
    def find_module(self, name, path=None):
        return self if name == "app" or name.startswith("app.") else None

    def find_spec(self, name, path=None, target=None):
        if name == "app" or name.startswith("app."):
            raise ImportError("legacy app package is unavailable: " + name)
        return None


sys.meta_path.insert(0, BlockLegacy())
sys.modules.pop("app", None)

import core.main
import core.processing
import core.realtime
import core.integrations.asr
import core.integrations.feedback
import core.integrations.gemini
import core.integrations.qwen_omni
import core.integrations.realtime_session
import core.integrations.realtime_asr

routes = {getattr(route, "path", "") for route in core.main.app.routes}
required = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/me",
    "/api/v1/auth/logout",
    "/api/v1/auth/password",
    "/api/v1/settings",
    "/api/v1/dashboard",
    "/api/v1/decks",
    "/api/v1/decks/tree",
    "/api/v1/my-courses",
    "/api/v1/review/queues",
    "/api/v1/dialogue/sessions",
    "/api/v1/review/realtime/asr/ws",
}
missing = required - routes
assert not missing, "missing routes: " + repr(sorted(missing))
for name in list(sys.modules):
    assert not (name == "app" or name.startswith("app.")), name
print("CORE_ONLY_OK")
"""


def test_core_imports_and_routes_without_legacy_app():
    env = {
        key: value
        for key, value in os.environ.items()
        if key in {"PATH", "HOME", "LANG", "LC_ALL", "TZ", "VIRTUAL_ENV"}
    }
    env.update(
        {
            "PYTHONPATH": str(BACKEND),
            "CORE_DATABASE_URL": "postgresql+psycopg://core-only@localhost/core_only",
            "CORE_CONFIRMATION_SECRET": "isolated-core-only-secret-value-1234",
            "CORE_ASR_API_KEY": "test",
            "CORE_GEMINI_API_KEY": "test",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", ISOLATED],
        cwd=BACKEND,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert "CORE_ONLY_OK" in result.stdout


def test_no_legacy_imports_in_core_source():
    offenders = []
    for path in (BACKEND / "core").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith(("import app", "from app")):
                offenders.append(f"{path.relative_to(BACKEND)}: {stripped}")
    assert offenders == []


def test_core_worker_processes_a_job_without_legacy_app(monkeypatch, engine, client, account):
    """The outbox consumer reaches providers through core integrations only."""
    from core import processing
    from core_tests.test_review import flip, make_note, next_card, queue

    calls = []

    def fake_transcribe(url):
        calls.append(("asr", url))
        return {"text": "Hello", "timestamps": []}

    def fake_provider():
        class Provider:
            def generate_single_feedback(self, **kwargs):
                calls.append(("ai", kwargs["front_text"]))
                return {"pronunciation": "ok", "completeness": "ok", "fluency": "ok",
                        "suggestions": [], "issues": []}

        return Provider()

    monkeypatch.setattr(processing, "transcribe", fake_transcribe)
    monkeypatch.setattr(processing, "feedback_provider", fake_provider)
    monkeypatch.setattr(
        processing, "audio_url", lambda db, asset_id, collection_id: "https://oss.test/recording.webm"
    )
    make_note(client, account, {"english": "Hello", "reference_audio": _asset(engine, account, ready=True)}, "sentence_retelling")
    q = queue(client, account)
    recording = _asset(engine, account)
    saved = flip(
        client,
        q,
        next_card(client, q),
        {"type": "audio", "temporary_media_asset_id": recording},
    )
    assert saved.status_code == 200, saved.text
    assert processing.process_one(engine)
    assert processing.process_one(engine)
    assert [kind for kind, _ in calls] == ["asr", "ai"]


def _asset(engine, account, ready=False):
    from uuid import uuid4

    from sqlalchemy.orm import Session

    from core.models import MediaAsset, utcnow

    with Session(engine) as db, db.begin():
        asset = MediaAsset(
            collection_id=__import__("uuid").UUID(account["collection"]["id"]),
            object_key=f"{uuid4()}.webm",
            kind="audio",
            lifecycle="ready" if ready else "temporary",
            # A recording is uploaded before it is claimed by a flip.
            uploaded_at=utcnow(),
            content_type="audio/webm",
            size_bytes=6,
        )
        db.add(asset)
        db.flush()
        return str(asset.id)
