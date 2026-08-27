"""Unit tests for Gemini adapter."""

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.adapters.gemini_adapter import GenerationConfig, GeminiAdapter, PromptTemplate
from app.exceptions import AIFeedbackError


@pytest.mark.unit
class TestGeminiAdapter:
    """Test suite for GeminiAdapter."""

    @pytest.fixture
    def gemini_adapter(self, monkeypatch):
        """Create GeminiAdapter instance with mocked genai client."""
        import app.adapters.gemini_adapter as module

        mock_client = Mock()
        mock_genai_client = Mock(return_value=mock_client)
        monkeypatch.setattr(module.genai, "Client", mock_genai_client)

        object.__setattr__(module.settings, "gemini_api_key", "test-api-key")
        object.__setattr__(module.settings, "gemini_model_id", "gemini-test-model")
        object.__setattr__(module.settings, "gemini_prompt_version", "v1")
        object.__setattr__(module.settings, "google_gemini_base_url", None)

        adapter = GeminiAdapter()
        monkeypatch.setattr(adapter, "_download_audio_bytes", lambda *_args, **_kwargs: b"audio-bytes")
        return adapter, mock_client

    def test_uses_official_sdk_without_relay_options(self, monkeypatch):
        import app.adapters.gemini_adapter as module

        mock_client = Mock()
        mock_genai_client = Mock(return_value=mock_client)
        monkeypatch.setattr(module.genai, "Client", mock_genai_client)

        object.__setattr__(module.settings, "gemini_api_key", "test-api-key")
        object.__setattr__(module.settings, "gemini_model_id", "gemini-test-model")
        object.__setattr__(module.settings, "gemini_prompt_version", "v1")
        object.__setattr__(module.settings, "google_gemini_base_url", None)

        GeminiAdapter()

        mock_genai_client.assert_called_once_with(api_key="test-api-key")

    def test_uses_configured_base_url(self, monkeypatch):
        import app.adapters.gemini_adapter as module

        mock_client = Mock()
        mock_genai_client = Mock(return_value=mock_client)
        monkeypatch.setattr(module.genai, "Client", mock_genai_client)

        object.__setattr__(module.settings, "gemini_api_key", "test-api-key")
        object.__setattr__(module.settings, "gemini_model_id", "gemini-test-model")
        object.__setattr__(module.settings, "gemini_prompt_version", "v1")
        object.__setattr__(module.settings, "google_gemini_base_url", "https://relay.example.com")

        GeminiAdapter()

        mock_genai_client.assert_called_once()
        _, kwargs = mock_genai_client.call_args
        assert kwargs["api_key"] == "test-api-key"
        assert kwargs["http_options"].base_url == "https://relay.example.com"

    def test_load_prompt_from_versioned_directory(self, gemini_adapter):
        adapter, _ = gemini_adapter

        expected_dir = Path(adapter.prompts_dir)
        assert expected_dir.name == "v1"
        assert (expected_dir / "single_feedback" / "system.md").exists()
        assert (expected_dir / "single_feedback" / "user.md").exists()
        assert (expected_dir / "single_feedback" / "metadata.json").exists()
        assert (expected_dir / "lesson_summary" / "system.md").exists()
        assert (expected_dir / "lesson_summary" / "user.md").exists()
        assert (expected_dir / "lesson_summary" / "metadata.json").exists()
        assert adapter.single_feedback_prompt.system
        assert adapter.single_feedback_prompt.user
        assert adapter.single_feedback_prompt.metadata["prompt_version"] == "1.0.0"
        assert adapter.lesson_summary_prompt.system
        assert adapter.lesson_summary_prompt.user

    def test_generate_single_feedback_success(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "transcription_text": "Last week I went to the theatre",
            "pronunciation": "Good overall pronunciation.",
            "completeness": "Most key content is present.",
            "fluency": "Generally fluent with minor hesitation.",
            "suggestions": [
                {
                    "text": "Stress the word theatre more clearly.",
                    "target_word": "theatre",
                    "timestamp": 1.2,
                }
            ],
            "issues": [
                {
                    "problem": "Dropped ending consonant in one word.",
                    "timestamp": 0.9,
                }
            ],
        }

        mock_response = Mock()
        mock_response.text = json.dumps(feedback_data)
        mock_client.models.generate_content.return_value = mock_response

        result = adapter.generate_single_feedback(
            front_text="Last week I went to the theatre.",
            user_audio_url="https://example.com/user.webm",
            reference_audio_url="https://example.com/ref.mp3",
        )

        assert result["pronunciation"] == "Good overall pronunciation."
        assert result["issues"][0]["timestamp"] == 0.9
        assert result["suggestions"][0]["target_word"] == "theatre"
        assert result["transcription_text"] == "Last week I went to the theatre"

    def test_generate_single_feedback_markdown_json(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "transcription_text": "Test sentence",
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent",
            "suggestions": [],
            "issues": [],
        }

        mock_response = Mock()
        mock_response.text = f"```json\n{json.dumps(feedback_data)}\n```"
        mock_client.models.generate_content.return_value = mock_response

        result = adapter.generate_single_feedback(
            front_text="Test sentence",
            user_audio_url="https://example.com/user.wav",
            reference_audio_url="https://example.com/ref.wav",
        )

        assert result["pronunciation"] == "Good"
        assert result["issues"] == []

    def test_generate_single_feedback_requires_transcription_text(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent",
            "suggestions": [],
            "issues": [],
        }

        mock_response = Mock()
        mock_response.text = json.dumps(feedback_data)
        mock_client.models.generate_content.return_value = mock_response

        with pytest.raises(AIFeedbackError) as exc_info:
            adapter.generate_single_feedback(
                front_text="Test sentence",
                user_audio_url="https://example.com/user.wav",
                reference_audio_url="https://example.com/ref.wav",
            )

        assert "Missing required field: transcription_text" in str(exc_info.value)

    def test_generate_single_feedback_missing_field(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "transcription_text": "test sentence",
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent",
            "suggestions": [],
            # missing issues
        }

        mock_response = Mock()
        mock_response.text = json.dumps(feedback_data)
        mock_client.models.generate_content.return_value = mock_response

        with pytest.raises(AIFeedbackError) as exc_info:
            adapter.generate_single_feedback(
                front_text="Test sentence",
                user_audio_url="https://example.com/user.wav",
                reference_audio_url="https://example.com/ref.wav",
            )

        assert "Missing required field: issues" in str(exc_info.value)

    def test_generate_single_feedback_invalid_issue_timestamp(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "transcription_text": "test sentence",
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent",
            "suggestions": [],
            "issues": [{"problem": "x", "timestamp": "bad"}],
        }

        mock_response = Mock()
        mock_response.text = json.dumps(feedback_data)
        mock_client.models.generate_content.return_value = mock_response

        with pytest.raises(AIFeedbackError) as exc_info:
            adapter.generate_single_feedback(
                front_text="Test sentence",
                user_audio_url="https://example.com/user.wav",
                reference_audio_url="https://example.com/ref.wav",
            )

        assert "issue.timestamp must be a number or null" in str(exc_info.value)

    def test_generate_single_feedback_supports_string_suggestions(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        feedback_data = {
            "transcription_text": "test sentence",
            "pronunciation": "Good",
            "completeness": "Complete",
            "fluency": "Fluent",
            "suggestions": ["Speak slightly slower"],
            "issues": [],
        }

        mock_response = Mock()
        mock_response.text = json.dumps(feedback_data)
        mock_client.models.generate_content.return_value = mock_response

        result = adapter.generate_single_feedback(
            front_text="Test sentence",
            user_audio_url="https://example.com/user.wav",
            reference_audio_url="https://example.com/ref.wav",
        )

        assert result["suggestions"][0]["text"] == "Speak slightly slower"
        assert result["suggestions"][0]["target_word"] is None

    def test_load_prompt_from_custom_directory(self, gemini_adapter, tmp_path: Path):
        adapter, _ = gemini_adapter
        prompt_dir = tmp_path / "prompt"
        prompt_dir.mkdir()
        (prompt_dir / "system.md").write_text("system", encoding="utf-8")
        (prompt_dir / "user.md").write_text("user", encoding="utf-8")
        (prompt_dir / "metadata.json").write_text(
            json.dumps({"prompt_version": "custom"}),
            encoding="utf-8",
        )

        prompt = adapter.load_prompt_from_dir(prompt_dir)

        assert prompt == PromptTemplate(
            system="system",
            user="user",
            metadata={"prompt_version": "custom"},
        )

    def test_generate_single_feedback_accepts_custom_prompt_and_generation_config(
        self,
        gemini_adapter,
    ):
        adapter, mock_client = gemini_adapter
        mock_response = Mock()
        mock_response.text = json.dumps(
            {
                "transcription_text": "Test sentence",
                "pronunciation": "Good",
                "completeness": "Complete",
                "fluency": "Fluent",
                "suggestions": [],
                "issues": [],
            }
        )
        mock_client.models.generate_content.return_value = mock_response

        adapter.generate_single_feedback(
            front_text="Test sentence",
            user_audio_url="https://example.com/user.wav",
            reference_audio_url="https://example.com/ref.wav",
            prompt_template=PromptTemplate(system="system", user="user"),
            generation_config=GenerationConfig(
                temperature=0.1,
                max_output_tokens=512,
            ),
        )

        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert config.temperature == 0.1
        assert config.max_output_tokens == 512

    def test_generate_single_feedback_uses_model_default_temperature_when_not_overridden(
        self,
        gemini_adapter,
    ):
        adapter, mock_client = gemini_adapter
        mock_response = Mock()
        mock_response.text = json.dumps(
            {
                "transcription_text": "Test sentence",
                "pronunciation": "Good",
                "completeness": "Complete",
                "fluency": "Fluent",
                "suggestions": [],
                "issues": [],
            }
        )
        mock_client.models.generate_content.return_value = mock_response

        adapter.generate_single_feedback(
            front_text="Test sentence",
            user_audio_url="https://example.com/user.wav",
            reference_audio_url="https://example.com/ref.wav",
        )

        config = mock_client.models.generate_content.call_args.kwargs["config"]
        assert getattr(config, "temperature", None) is None
        assert config.max_output_tokens == 2048

    def test_generate_single_feedback_makes_single_audio_request_without_retry(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        mock_client.models.generate_content.side_effect = RuntimeError("bad request")

        with pytest.raises(AIFeedbackError) as exc_info:
            adapter.generate_single_feedback(
                front_text="Test sentence",
                user_audio_url="https://example.com/user.wav",
                reference_audio_url="https://example.com/ref.wav",
            )

        assert "Gemini audio request failed: bad request" in str(exc_info.value)
        assert mock_client.models.generate_content.call_count == 1

    def test_generate_lesson_summary_success(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        summary_data = {
            "overall": "Steady progress in this lesson.",
            "patterns": ["Minor ending-sound omissions"],
            "prioritized_actions": ["Practice final consonants"],
        }

        mock_response = Mock()
        mock_response.text = json.dumps(summary_data)
        mock_client.models.generate_content.return_value = mock_response

        result = adapter.generate_lesson_summary(feedbacks=[{"issues": []}])

        assert result["overall"].startswith("Steady")
        assert len(result["patterns"]) == 1

    def test_generate_lesson_summary_missing_field(self, gemini_adapter):
        adapter, mock_client = gemini_adapter

        summary_data = {
            "overall": "Good",
            "patterns": ["Pattern"],
            # missing prioritized_actions
        }

        mock_response = Mock()
        mock_response.text = json.dumps(summary_data)
        mock_client.models.generate_content.return_value = mock_response

        with pytest.raises(AIFeedbackError) as exc_info:
            adapter.generate_lesson_summary(feedbacks=[{"issues": []}])

        assert "Missing required field: prioritized_actions" in str(exc_info.value)

    def test_missing_prompt_file_raises(self, monkeypatch):
        import app.adapters.gemini_adapter as module

        mock_client = Mock()
        monkeypatch.setattr(module.genai, "Client", Mock(return_value=mock_client))

        object.__setattr__(module.settings, "gemini_api_key", "test-api-key")
        object.__setattr__(module.settings, "gemini_model_id", "gemini-test-model")
        object.__setattr__(module.settings, "gemini_prompt_version", "v999_not_exist")

        with pytest.raises(AIFeedbackError) as exc_info:
            GeminiAdapter()

        assert "Prompt directory not found" in str(exc_info.value)
