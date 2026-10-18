"""Tests for AI feedback provider selection."""

from unittest.mock import Mock, patch

import pytest

from app.adapters.ai_feedback_adapter import (
    create_ai_feedback_provider,
    registered_ai_feedback_providers,
)
from app.exceptions import AIFeedbackError


def test_create_provider_uses_explicit_provider_id():
    instance = Mock()
    with patch("app.adapters.gemini_adapter.GeminiAdapter", return_value=instance):
        assert create_ai_feedback_provider(" GEMINI ") is instance


def test_create_provider_defaults_to_configured_provider():
    instance = Mock()
    with (
        patch("app.adapters.ai_feedback_adapter.settings.ai_feedback_provider", "gemini"),
        patch("app.adapters.gemini_adapter.GeminiAdapter", return_value=instance),
    ):
        assert create_ai_feedback_provider() is instance


def test_create_provider_rejects_unregistered_provider():
    with pytest.raises(AIFeedbackError, match="Unsupported AI_FEEDBACK_PROVIDER: unknown"):
        create_ai_feedback_provider("unknown")


def test_registered_provider_ids_are_stable_and_sorted():
    assert registered_ai_feedback_providers() == ("gemini", "qwen_omni")


def test_translation_feedback_uses_text_provider_and_preserves_source_data():
    from app.adapters.feedback_base import FeedbackAdapterBase
    adapter = object.__new__(FeedbackAdapterBase)
    adapter._generate_text_only = Mock(return_value='{"summary":"表达正确","completeness":"完整","fluency":"自然","suggestions":["注意标点"]}')
    result = adapter.generate_translation_feedback('你好', 'Hello', '  Hi  ')
    assert result['summary'] == '表达正确'
    assert result['suggestions'][0]['text'] == '注意标点'
    prompt = adapter._generate_text_only.call_args.args[0]
    assert '"translation": "  Hi  "' in prompt
    assert 'pronunciation' not in result


@pytest.mark.parametrize('response', ['[]', '{}', '{"summary":1,"completeness":"ok","fluency":"ok"}'])
def test_translation_feedback_rejects_invalid_response(response):
    from app.adapters.feedback_base import FeedbackAdapterBase
    adapter = object.__new__(FeedbackAdapterBase)
    adapter._generate_text_only = Mock(return_value=response)
    with pytest.raises(AIFeedbackError):
        adapter.generate_translation_feedback('你好', 'Hello', 'Hi')
