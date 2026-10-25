import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from google.genai import errors

from core import processing
from core.config import get_settings
from core.integrations import feedback, gemini
from core.integrations.errors import AIFeedbackError
from core.integrations.feedback import GenerationConfig


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CORE_GEMINI_API_KEY", "secret-test-key")
    monkeypatch.setenv("CORE_GEMINI_BASE_URL", "https://relay.example")
    get_settings.cache_clear()
    client = Mock()
    monkeypatch.setattr(gemini.genai, "Client", Mock(return_value=client))
    value = gemini.GeminiProvider()
    yield value
    value.close()
    get_settings.cache_clear()


@pytest.mark.parametrize("mode", ["text", "audio"])
@pytest.mark.parametrize("error,kind,status", [
    (httpx.ReadTimeout("secret-body signed-url secret-test-key"), "ReadTimeout", None),
    (errors.ClientError(429, {"error": {"message": "secret-body"}}), "ClientError", 429),
    (errors.ServerError(503, {"error": {"message": "secret-body"}}), "ServerError", 503),
])
def test_upstream_failures_are_diagnosable_without_sensitive_data(provider, caplog, mode, error, kind, status):
    provider.client.models.generate_content.side_effect = error
    with caplog.at_level(logging.INFO), pytest.raises(AIFeedbackError) as caught:
        if mode == "text":
            provider._generate_text_only("secret-prompt", GenerationConfig())
        else:
            provider._generate_with_audio("secret-prompt", "https://oss/user?secret-sign", "https://oss/ref?secret-sign", GenerationConfig())
    assert caught.value.reason == "upstream_request"
    assert f"error={kind} status={status}" in caplog.text
    assert "endpoint=relay.example" in caplog.text
    for secret in ("secret-body", "secret-test-key", "secret-prompt", "secret-sign"):
        assert secret not in caplog.text + str(caught.value)


def test_audio_urls_are_passed_through_without_download(provider, caplog):
    provider.client.models.generate_content.return_value = SimpleNamespace(text='{}')
    with caplog.at_level(logging.INFO):
        assert provider._generate_with_audio(
            "prompt",
            "https://oss/user.webm?Signature=x",
            "https://oss/ref.mp3?Signature=y",
            GenerationConfig(),
        ) == '{}'
    assert "Gemini request: mode=audio" in caplog.text
    call = provider.client.models.generate_content.call_args.kwargs
    assert call["config"].automatic_function_calling.disable is True
    reference, user = call["contents"][1], call["contents"][2]
    assert reference.file_data.file_uri == "https://oss/ref.mp3?Signature=y"
    assert reference.file_data.mime_type == "audio/mpeg"
    assert user.file_data.file_uri == "https://oss/user.webm?Signature=x"
    assert user.file_data.mime_type == "audio/webm"
    assert reference.inline_data is None and user.inline_data is None


def test_invalid_json_is_distinct_from_upstream_failure(provider):
    provider.client.models.generate_content.return_value = SimpleNamespace(text='invalid secret-body')
    with pytest.raises(AIFeedbackError) as caught:
        provider.generate_translation_feedback("你好", "Hello", "Hi")
    assert caught.value.reason == "invalid_json"
    assert "secret-body" not in str(caught.value)


def test_sdk_does_not_retry_429_inside_one_outbox_attempt(monkeypatch):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            calls.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = b'{"error":{"code":429,"message":"secret-body","status":"RESOURCE_EXHAUSTED"}}'
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setenv("CORE_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CORE_GEMINI_BASE_URL", f"http://127.0.0.1:{server.server_port}")
    get_settings.cache_clear()
    try:
        value = gemini.GeminiProvider()
        try:
            with pytest.raises(AIFeedbackError):
                value._generate_text_only("ping", GenerationConfig())
            assert len(calls) == 1
        finally:
            value.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
        get_settings.cache_clear()


def test_worker_reuses_one_provider_per_thread_and_closes_it(monkeypatch):
    barrier = threading.Barrier(2)
    factory = Mock(side_effect=lambda: Mock())
    monkeypatch.setattr(feedback, "create_provider", factory)

    def consume():
        first = processing.feedback_provider()
        barrier.wait(timeout=5)
        try:
            assert processing.feedback_provider() is first
            return first
        finally:
            processing.close_feedback_provider()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: consume(), range(2)))
    assert results[0] is not results[1]
    assert factory.call_count == 2
    for result in results:
        result.close.assert_called_once_with()


def test_worker_loop_closes_provider_after_stop(monkeypatch):
    stop = threading.Event()
    factory = Mock(return_value=Mock())
    monkeypatch.setattr(feedback, "create_provider", factory)

    def process():
        processing.feedback_provider()
        stop.set()
        return True

    monkeypatch.setattr(processing, "process_one", process)
    processing.process_loop(stop)
    factory.return_value.close.assert_called_once_with()
