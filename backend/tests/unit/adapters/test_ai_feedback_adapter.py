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
