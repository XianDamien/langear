"""Google Gemini feedback provider through the official google-genai SDK."""

from typing import Any

from google import genai
from google.genai import types

from core.config import get_settings
from core.integrations.errors import AIFeedbackError
from core.integrations.feedback import FeedbackAdapterBase, GenerationConfig


class GeminiProvider(FeedbackAdapterBase):
    provider_id = "gemini"

    def __init__(self):
        settings = get_settings()
        if not settings.gemini_api_key:
            raise AIFeedbackError("Missing Gemini API key")
        kwargs: dict[str, Any] = {
            "api_key": settings.gemini_api_key.get_secret_value()
        }
        base_url = (settings.gemini_base_url or "").strip()
        if base_url:
            kwargs["http_options"] = types.HttpOptions(base_url=base_url)
        self.client = genai.Client(**kwargs)
        self.model_id = settings.gemini_model_id.strip()
        self._base_url = base_url
        super().__init__()

    def _generate_with_audio(
        self,
        prompt: str,
        user_audio_url: str,
        reference_audio_url: str,
        generation_config: GenerationConfig,
    ) -> str:
        config_kwargs = {
            "max_output_tokens": generation_config.max_output_tokens,
            "response_mime_type": "application/json",
        }
        if generation_config.temperature is not None:
            config_kwargs["temperature"] = generation_config.temperature
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=self._download_audio(reference_audio_url),
                        mime_type=self._mime_type(reference_audio_url),
                    ),
                    types.Part.from_bytes(
                        data=self._download_audio(user_audio_url),
                        mime_type=self._mime_type(user_audio_url),
                    ),
                ],
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except AIFeedbackError:
            raise
        except Exception:
            raise AIFeedbackError("Gemini audio request failed") from None
        return response.text or ""

    def _generate_text_only(
        self, prompt: str, generation_config: GenerationConfig
    ) -> str:
        config_kwargs = {
            "max_output_tokens": generation_config.max_output_tokens,
            "response_mime_type": "application/json",
        }
        if generation_config.temperature is not None:
            config_kwargs["temperature"] = generation_config.temperature
        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
        except Exception:
            raise AIFeedbackError("Gemini text request failed") from None
        return response.text or ""
