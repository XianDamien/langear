"""Google Gemini feedback provider through the official google-genai SDK."""

import logging
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from google import genai
from google.genai import types

from core.config import get_settings
from core.integrations.errors import AIFeedbackError
from core.integrations.feedback import FeedbackAdapterBase, GenerationConfig

logger = logging.getLogger(__name__)


class GeminiProvider(FeedbackAdapterBase):
    provider_id = "gemini"

    def __init__(self):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise AIFeedbackError("Missing Gemini API key", reason="configuration")
        kwargs: dict[str, Any] = {
            "api_key": settings.gemini_api_key.get_secret_value()
        }
        base_url = (settings.gemini_base_url or "").strip()
        http_options: dict[str, Any] = {
            "timeout": settings.gemini_request_timeout_ms,
            # The durable outbox owns retries; SDK retries multiply slot occupancy.
            "retry_options": types.HttpRetryOptions(attempts=1),
        }
        if base_url:
            http_options["base_url"] = base_url
        kwargs["http_options"] = types.HttpOptions(**http_options)
        self.client = genai.Client(**kwargs)
        self.model_id = settings.gemini_model_id.strip()
        self._base_url = base_url
        self._endpoint = urlsplit(base_url or "https://generativelanguage.googleapis.com").hostname
        super().__init__()

    def close(self):
        self.client.close()

    def _request(self, contents, generation_config, mode):
        config_kwargs = {
            "max_output_tokens": generation_config.max_output_tokens,
            "response_mime_type": "application/json",
            "automatic_function_calling": types.AutomaticFunctionCallingConfig(disable=True),
        }
        if generation_config.temperature is not None:
            config_kwargs["temperature"] = generation_config.temperature
        started = monotonic()
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=contents,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            return response.text or ""
        except Exception as exc:
            # Never interpolate the exception: SDK messages can contain response
            # bodies, credentials, prompts, or signed URLs.
            code = getattr(exc, "code", None)
            status = code if type(code) is int and 100 <= code <= 599 else None
            logger.warning(
                "Gemini request failed: mode=%s error=%s status=%s",
                mode, type(exc).__name__, status,
            )
            raise AIFeedbackError("Gemini " + mode + " request failed", reason="upstream_request") from None
        finally:
            logger.info(
                "Gemini request: mode=%s model=%s endpoint=%s elapsed_s=%.3f",
                mode, self.model_id, self._endpoint, monotonic() - started,
            )

    def _generate_with_audio(
        self,
        prompt: str,
        user_audio_url: str,
        reference_audio_url: str,
        generation_config: GenerationConfig,
    ) -> str:
        started = monotonic()
        reference = self._download_audio(reference_audio_url)
        user = self._download_audio(user_audio_url)
        logger.info(
            "Gemini audio prepared: reference_bytes=%s user_bytes=%s elapsed_s=%.3f",
            len(reference), len(user), monotonic() - started,
        )
        return self._request(
            [prompt,
             types.Part.from_bytes(data=reference, mime_type=self._mime_type(reference_audio_url)),
             types.Part.from_bytes(data=user, mime_type=self._mime_type(user_audio_url))],
            generation_config, "audio",
        )

    def _generate_text_only(
        self, prompt: str, generation_config: GenerationConfig
    ) -> str:
        return self._request(prompt, generation_config, "text")
