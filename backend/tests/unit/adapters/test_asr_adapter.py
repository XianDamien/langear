"""Unit tests for ASR adapter."""

from unittest.mock import Mock, patch

import pytest

from app.adapters.asr_adapter import ASRAdapter
from app.exceptions import ASRTranscriptionError


@pytest.mark.unit
class TestASRAdapter:
    @pytest.fixture
    def asr_adapter(self):
        with patch("app.adapters.asr_adapter.dashscope"):
            yield ASRAdapter()

    def test_transcribe_success_multimodal(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "Hello world this is a test"},
                        ]
                    }
                }
            ]
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            result = asr_adapter.transcribe(audio_url)

        assert result["text"] == "Hello world this is a test"
        assert result["timestamps"] == []

    def test_transcribe_multiple_content_parts(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "First"},
                            {"text": "Second"},
                        ]
                    }
                }
            ]
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            result = asr_adapter.transcribe(audio_url)

        assert result["text"] == "First Second"

    def test_transcribe_api_error_status(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.message = "Internal server error"
        mock_response.output = None

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            with pytest.raises(ASRTranscriptionError) as exc_info:
                asr_adapter.transcribe(audio_url)

        assert "ASR API returned status 500" in str(exc_info.value)

    def test_transcribe_empty_response(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = None

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            with pytest.raises(ASRTranscriptionError) as exc_info:
                asr_adapter.transcribe(audio_url)

        assert "No transcription in response" in str(exc_info.value)

    def test_transcribe_empty_content(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "choices": [{"message": {"content": []}}],
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            with pytest.raises(ASRTranscriptionError) as exc_info:
                asr_adapter.transcribe(audio_url)

        assert "No transcription in response" in str(exc_info.value)

    def test_transcribe_exception(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.side_effect = Exception("Network timeout")
            with pytest.raises(ASRTranscriptionError) as exc_info:
                asr_adapter.transcribe(audio_url)

        assert "ASR transcription failed" in str(exc_info.value)

    def test_transcribe_legacy_results_compatibility(self, asr_adapter):
        audio_url = "https://oss.example.com/test.wav"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "results": [
                {
                    "transcription_text": "Legacy output text",
                    "sentence": [
                        {
                            "words": [
                                {"text": "Legacy", "begin_time": 0, "end_time": 500},
                                {"text": "output", "begin_time": 500, "end_time": 1000},
                            ]
                        }
                    ],
                }
            ]
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            result = asr_adapter.transcribe(audio_url)

        assert result["text"] == "Legacy output text"
        assert result["timestamps"] == [
            {"word": "Legacy", "start": 0.0, "end": 0.5},
            {"word": "output", "start": 0.5, "end": 1.0},
        ]

    def test_transcribe_strips_whitespace(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "  Text with whitespace  \n"},
                        ]
                    }
                }
            ]
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            result = asr_adapter.transcribe(audio_url)

        assert result["text"] == "Text with whitespace"

    def test_transcribe_call_parameters(self, asr_adapter):
        audio_url = "https://oss.example.com/test.webm"

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.output = {
            "choices": [
                {
                    "message": {
                        "content": [
                            {"text": "Test"},
                        ]
                    }
                }
            ]
        }

        with patch("app.adapters.asr_adapter.dashscope.MultiModalConversation.call") as mock_call:
            mock_call.return_value = mock_response
            asr_adapter.transcribe(audio_url, timeout=120)

        mock_call.assert_called_once_with(
            model="qwen3-asr-flash",
            messages=[{"role": "user", "content": [{"audio": audio_url}]}],
            asr_options={"enable_itn": False},
        )
