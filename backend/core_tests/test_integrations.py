"""Provider configuration comes from repo-standard environment variables."""

import dashscope
import pytest
from sqlalchemy import select

from core.config import Settings, get_settings
from core.integrations import asr


def test_gemini_relay_uses_repo_standard_env_name(monkeypatch):
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://relay.example/v1")
    monkeypatch.delenv("CORE_GEMINI_BASE_URL", raising=False)
    settings = Settings(
        database_url="postgresql+psycopg://user@localhost:5432/db",
        confirmation_secret="x" * 40,
    )
    assert settings.gemini_base_url == "https://relay.example/v1"


def test_gemini_relay_can_be_configured_under_the_core_prefix(monkeypatch):
    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL", raising=False)
    monkeypatch.setenv("CORE_GEMINI_BASE_URL", "https://core.relay/v1")
    settings = Settings(
        database_url="postgresql+psycopg://user@localhost:5432/db",
        confirmation_secret="x" * 40,
    )
    assert settings.gemini_base_url == "https://core.relay/v1"


def test_gemini_request_timeout_defaults_and_reads_repo_standard_env(monkeypatch):
    monkeypatch.delenv("GEMINI_REQUEST_TIMEOUT_MS", raising=False)
    monkeypatch.delenv("CORE_GEMINI_REQUEST_TIMEOUT_MS", raising=False)
    defaults = Settings(
        database_url="postgresql+psycopg://user@localhost:5432/db",
        confirmation_secret="x" * 40,
        _env_file=None,
    )
    assert defaults.gemini_request_timeout_ms == 60_000

    monkeypatch.setenv("GEMINI_REQUEST_TIMEOUT_MS", "45000")
    configured = Settings(
        database_url="postgresql+psycopg://user@localhost:5432/db",
        confirmation_secret="x" * 40,
        _env_file=None,
    )
    assert configured.gemini_request_timeout_ms == 45000


def test_gemini_provider_applies_request_timeout(monkeypatch):
    from google.genai import types

    from core import config
    from core.integrations import gemini

    monkeypatch.setenv("CORE_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORE_GEMINI_BASE_URL", "https://relay.example/v1")
    monkeypatch.setenv("CORE_GEMINI_REQUEST_TIMEOUT_MS", "45000")
    config.get_settings.cache_clear()
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(gemini.genai, "Client", FakeClient)
    try:
        gemini.GeminiProvider()
    finally:
        config.get_settings.cache_clear()

    options = captured["http_options"]
    assert isinstance(options, types.HttpOptions)
    assert options.retry_options.attempts == 1
    assert options.timeout == 45000
    assert options.base_url == "https://relay.example/v1"


def test_gemini_request_timeout_interrupts_a_hanging_endpoint(monkeypatch):
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from core import config
    from core.integrations.errors import AIFeedbackError
    from core.integrations.feedback import GenerationConfig
    from core.integrations.gemini import GeminiProvider

    class HangingHandler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            time.sleep(5)
            try:
                self.send_response(200)
                self.end_headers()
            except OSError:
                pass

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), HangingHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("CORE_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv(
        "CORE_GEMINI_BASE_URL", f"http://127.0.0.1:{server.server_port}"
    )
    monkeypatch.setenv("CORE_GEMINI_REQUEST_TIMEOUT_MS", "500")
    config.get_settings.cache_clear()
    try:
        provider = GeminiProvider()
        assert provider.client._api_client._http_options.timeout == 500
        started = time.monotonic()
        with pytest.raises(AIFeedbackError):
            provider._generate_text_only("ping", GenerationConfig())
        assert time.monotonic() - started < 4
    finally:
        server.shutdown()
        config.get_settings.cache_clear()


def test_asr_always_calls_the_contracted_model(monkeypatch):
    from core import config

    monkeypatch.setenv("CORE_ASR_MODEL", "some-other-model")
    monkeypatch.setenv("CORE_ASR_API_KEY", "test-key")
    config.get_settings.cache_clear()
    calls = []

    class Response:
        status_code = 200
        output = {"text": "hello"}

    def call(**kwargs):
        calls.append(kwargs)
        return Response()

    monkeypatch.setattr(dashscope.MultiModalConversation, "call", call)
    try:
        assert asr.transcribe("https://oss.example/audio.webm")["text"] == "hello"
    finally:
        config.get_settings.cache_clear()
    assert calls[0]["model"] == "qwen3-asr-flash"
