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
