"""Alibaba Cloud Qwen Omni through its OpenAI-compatible HTTPS API."""

import base64
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from core.config import get_settings
from core.integrations.errors import AIFeedbackError
from core.integrations.feedback import FeedbackAdapterBase, GenerationConfig


class QwenOmniProvider(FeedbackAdapterBase):
    provider_id = "qwen_omni"

    def __init__(self):
        settings = get_settings()
        if not settings.qwen_omni_api_key:
            raise AIFeedbackError("Missing Qwen Omni API key")
        self.model_id = settings.qwen_omni_model_id.strip()
        if not self.model_id:
            raise AIFeedbackError("Missing Qwen Omni model id")
        base_url = settings.qwen_omni_base_url.strip().rstrip("/")
        parsed = urlparse(base_url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise AIFeedbackError("Qwen Omni base URL must be an HTTPS API base URL")
        self._endpoint = base_url + "/chat/completions"
        self._api_key = settings.qwen_omni_api_key.get_secret_value()
        super().__init__()

    def _audio_part(self, audio_url: str) -> dict:
        audio_format = Path(urlparse(audio_url).path).suffix.lower().lstrip(".")
        if audio_format not in {"wav", "mp3", "webm", "m4a", "ogg", "flac", "aac"}:
            raise AIFeedbackError("Unsupported Qwen Omni audio format")
        mime_type = {
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
        }.get(audio_format, "audio/" + audio_format)
        encoded = base64.b64encode(self._download_audio(audio_url)).decode("ascii")
        return {
            "type": "input_audio",
            "input_audio": {
                "data": f"data:{mime_type};base64,{encoded}",
                "format": audio_format,
            },
        }

    def _request(self, content: list[dict], generation_config: GenerationConfig) -> str:
        payload = {
            "model": self.model_id,
            "messages": [{"role": "user", "content": content}],
            "modalities": ["text"],
            "response_format": {"type": "json_object"},
            "reasoning_effort": "none",
            "stream": False,
            "max_tokens": generation_config.max_output_tokens,
        }
        if generation_config.temperature is not None:
            payload["temperature"] = generation_config.temperature
        request = Request(
            self._endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self._api_key,
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=120) as response:
                result = json.load(response)
        except HTTPError as exc:
            raise AIFeedbackError(
                f"Qwen Omni request failed (HTTP {exc.code})"
            ) from None
        except (URLError, TimeoutError, OSError):
            raise AIFeedbackError("Qwen Omni request failed (connection or timeout)") from None
        except (ValueError, TypeError):
            raise AIFeedbackError("Qwen Omni returned an invalid JSON envelope") from None
        try:
            choice = result["choices"][0]
            if choice.get("finish_reason") != "stop":
                raise AIFeedbackError("Qwen Omni response did not finish normally")
            text = choice["message"]["content"]
        except (KeyError, IndexError, TypeError):
            raise AIFeedbackError("Qwen Omni returned an invalid completion envelope") from None
        if not isinstance(text, str) or not text.strip():
            raise AIFeedbackError("Qwen Omni returned empty text")
        return text

    def _generate_with_audio(
        self,
        prompt: str,
        user_audio_url: str,
        reference_audio_url: str,
        generation_config: GenerationConfig,
    ) -> str:
        return self._request(
            [
                {"type": "text", "text": prompt},
                self._audio_part(reference_audio_url),
                self._audio_part(user_audio_url),
            ],
            generation_config,
        )

    def _generate_text_only(
        self, prompt: str, generation_config: GenerationConfig
    ) -> str:
        return self._request([{"type": "text", "text": prompt}], generation_config)
