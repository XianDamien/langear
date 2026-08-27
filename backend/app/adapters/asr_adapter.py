"""Alibaba Cloud ASR adapter for speech transcription."""

from typing import Any

from app.config import settings
from app.exceptions import ASRTranscriptionError
import dashscope


class ASRAdapter:
    """Adapter for Alibaba Cloud ASR (Automatic Speech Recognition).

    Uses DashScope qwen3-asr-flash model for speech-to-text transcription
    with word-level timestamps.
    """

    def __init__(self):
        """Initialize ASR client with API key from settings."""
        dashscope.api_key = settings.dashscope_api_key
        self.model = "qwen3-asr-flash"

    def transcribe(
        self,
        audio_url: str,
        timeout: int = 60,
    ) -> dict[str, Any]:
        """Transcribe audio to text using qwen3-asr-flash model.

        Args:
            audio_url: OSS signed URL of the audio file
            timeout: Request timeout in seconds (default: 60)

        Returns:
            Dictionary containing:
            - text: Complete transcription text
            - timestamps: List of word-level timestamps
                [{word: str, start: float, end: float}, ...]

        Raises:
            ASRTranscriptionError: If transcription fails
        """
        _ = timeout  # preserved for backward-compatible signature

        try:
            # qwen3-asr-flash accepts signed OSS URL via multimodal conversation API.
            response = dashscope.MultiModalConversation.call(
                model=self.model,
                messages=[{"role": "user", "content": [{"audio": audio_url}]}],
                asr_options={"enable_itn": False},
            )

            if response.status_code != 200:
                raise ASRTranscriptionError(
                    f"ASR API returned status {response.status_code}: {response.message}"
                )

            text = self._extract_text(response.output).strip()
            if not text:
                raise ASRTranscriptionError("No transcription in response")

            return {
                "text": text,
                "timestamps": self._extract_timestamps(response.output),
            }

        except ASRTranscriptionError:
            raise
        except Exception as e:
            raise ASRTranscriptionError(f"ASR transcription failed: {str(e)}")

    @staticmethod
    def _extract_text(output: Any) -> str:
        """Extract transcription text from DashScope response output.

        Supports both:
        - qwen3-asr-flash multimodal structure: output.choices[].message.content[].text
        - legacy recognition structure: output.results[].transcription_text
        """
        if not isinstance(output, dict):
            return ""

        # New qwen3-asr-flash multimodal response
        choices = output.get("choices")
        if isinstance(choices, list):
            parts: list[str] = []
            for choice in choices:
                if not isinstance(choice, dict):
                    continue
                message = choice.get("message")
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text")
                        if isinstance(text, str) and text:
                            parts.append(text)
            if parts:
                return " ".join(parts)

        # Legacy compatibility format
        results = output.get("results")
        if isinstance(results, list) and results:
            first = results[0]
            if isinstance(first, dict):
                text = first.get("transcription_text")
                if isinstance(text, str):
                    return text

        text = output.get("text")
        return text if isinstance(text, str) else ""

    @staticmethod
    def _extract_timestamps(output: Any) -> list[dict[str, Any]]:
        """Extract word-level timestamps when available.

        qwen3-asr-flash multimodal responses may not include word timestamps.
        We keep compatibility for legacy `results[].sentence[].words[]` payloads.
        """
        if not isinstance(output, dict):
            return []

        results = output.get("results")
        if not isinstance(results, list) or not results:
            return []

        first = results[0]
        if not isinstance(first, dict):
            return []

        sentences = first.get("sentence")
        if not isinstance(sentences, list):
            return []

        timestamps: list[dict[str, Any]] = []
        for sentence in sentences:
            if not isinstance(sentence, dict):
                continue
            words = sentence.get("words")
            if not isinstance(words, list):
                continue
            for word_info in words:
                if not isinstance(word_info, dict):
                    continue
                timestamps.append(
                    {
                        "word": word_info.get("text", ""),
                        "start": word_info.get("begin_time", 0) / 1000.0,
                        "end": word_info.get("end_time", 0) / 1000.0,
                    }
                )
        return timestamps
