"""Qwen transport and shared feedback contract regression tests."""

import base64
import io
import json
from unittest.mock import Mock
from urllib.error import HTTPError

import pytest

from app.adapters.ai_feedback_adapter import GenerationConfig, create_ai_feedback_provider
from app.adapters.qwen_omni_adapter import QwenOmniAdapter
from app.config import settings
from app.exceptions import AIFeedbackError

FEEDBACK = {
    "transcription_text": "I went to the theatre.",
    "pronunciation": "发音清晰", "completeness": "内容完整", "fluency": "表达连贯",
    "suggestions": [{"text": "练习重音", "target_word": "theatre", "timestamp": 1.2}],
    "issues": [],
}


@pytest.fixture
def adapter(monkeypatch):
    monkeypatch.setattr(settings, "qwen_omni_api_key", "secret-test-key")
    monkeypatch.setattr(settings, "qwen_omni_base_url", "https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1")
    return QwenOmniAdapter()


def mock_response(monkeypatch, content, finish_reason="stop"):
    response = io.BytesIO(json.dumps({
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}]
    }).encode())
    transport = Mock(return_value=response)
    monkeypatch.setattr("app.adapters.qwen_omni_adapter.urlopen", transport)
    return transport


def test_dual_audio_order_json_mode_and_output_contract(adapter, monkeypatch, tmp_path):
    ref = tmp_path / "ref.mp3"
    user = tmp_path / "user.webm"
    ref.write_bytes(b"reference")
    user.write_bytes(b"student")
    transport = mock_response(monkeypatch, json.dumps(FEEDBACK))
    result = adapter.generate_single_feedback(
        "I went to the theatre.", user.as_uri(), ref.as_uri(),
        generation_config=GenerationConfig(temperature=0.2, max_output_tokens=900),
    )
    assert result == FEEDBACK
    request = transport.call_args.args[0]
    assert request.full_url.endswith("/compatible-mode/v1/chat/completions")
    payload = json.loads(request.data)
    assert payload["model"] == "qwen3.8-omni-flash"
    assert payload["reasoning_effort"] == "none"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["stream"] is False
    assert payload["modalities"] == ["text"]
    assert payload["temperature"] == 0.2
    assert payload["max_tokens"] == 900
    parts = payload["messages"][0]["content"]
    assert [p["input_audio"]["format"] for p in parts[1:]] == ["mp3", "webm"]
    assert [base64.b64decode(p["input_audio"]["data"].split(",", 1)[1]) for p in parts[1:]] == [b"reference", b"student"]
    assert transport.call_count == 1


def test_summary_and_model_default_temperature(adapter, monkeypatch):
    summary = {"overall": "练习完成", "patterns": [], "prioritized_actions": []}
    transport = mock_response(monkeypatch, json.dumps(summary))
    assert adapter.generate_lesson_summary([FEEDBACK]) == summary
    payload = json.loads(transport.call_args.args[0].data)
    assert "temperature" not in payload
    assert len(payload["messages"][0]["content"]) == 1


def test_http_failure_redacts_details_and_does_not_retry(adapter, monkeypatch):
    transport = Mock(side_effect=HTTPError("https://example.com", 401, "secret-test-key", {}, None))
    monkeypatch.setattr("app.adapters.qwen_omni_adapter.urlopen", transport)
    with pytest.raises(AIFeedbackError, match="HTTP 401") as exc:
        adapter.generate_lesson_summary([])
    assert "secret-test-key" not in str(exc.value)
    assert transport.call_count == 1


@pytest.mark.parametrize("content,finish", [("", "stop"), ("{}", "length"), (None, "stop")])
def test_rejects_empty_or_truncated_completions(adapter, monkeypatch, content, finish):
    mock_response(monkeypatch, content, finish)
    with pytest.raises(AIFeedbackError):
        adapter.generate_lesson_summary([])


def test_shared_schema_is_enforced(adapter, monkeypatch):
    mock_response(monkeypatch, '{"overall": "missing lists"}')
    with pytest.raises(AIFeedbackError, match="Missing required field"):
        adapter.generate_lesson_summary([])


def test_factory_selects_qwen_without_initializing_google(adapter, monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", None)
    assert isinstance(create_ai_feedback_provider("qwen_omni"), QwenOmniAdapter)


def test_missing_key_rejected(monkeypatch):
    monkeypatch.setattr(settings, "qwen_omni_api_key", None)
    with pytest.raises(AIFeedbackError, match="Missing Qwen Omni API key"):
        QwenOmniAdapter()
