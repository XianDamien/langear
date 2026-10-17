"""Google Gemini adapter for AI evaluation."""

from typing import Any

from google import genai
from google.genai import types

from app.adapters.ai_feedback_adapter import GenerationConfig, PromptTemplate
from app.adapters.feedback_base import FeedbackAdapterBase
from app.config import settings
from app.exceptions import AIFeedbackError


class GeminiAdapter(FeedbackAdapterBase):
    """Adapter for Google Gemini AI multimodal evaluation."""

    provider_id = "gemini"

    def __init__(self):
        """Initialize Gemini client, model, and prompt templates."""
        api_key = (settings.gemini_api_key or "").strip()
        if not api_key:
            raise AIFeedbackError("Missing Gemini API key")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if settings.google_gemini_base_url:
            client_kwargs["http_options"] = types.HttpOptions(
                base_url=settings.google_gemini_base_url
            )

        self.client = genai.Client(**client_kwargs)
        self.model_id = settings.gemini_model_id.strip()
        super().__init__()

    def _generate_with_audio(
        self,
        prompt: str,
        user_audio_url: str,
        reference_audio_url: str,
        generation_config: GenerationConfig,
    ) -> str:
        """Generate multimodal response with official SDK inline audio only."""
        config_kwargs: dict[str, Any] = {
            "max_output_tokens": generation_config.max_output_tokens,
            "response_mime_type": "application/json",
        }
        if generation_config.temperature is not None:
            config_kwargs["temperature"] = generation_config.temperature

        config = types.GenerateContentConfig(
            **config_kwargs,
        )

        user_mime = self._guess_audio_mime_type(user_audio_url)
        reference_mime = self._guess_audio_mime_type(reference_audio_url)

        try:
            response = self.client.models.generate_content(
                model=self.model_id,
                contents=[
                    prompt,
                    types.Part.from_bytes(
                        data=self._download_audio_bytes(reference_audio_url),
                        mime_type=reference_mime,
                    ),
                    types.Part.from_bytes(
                        data=self._download_audio_bytes(user_audio_url),
                        mime_type=user_mime,
                    ),
                ],
                config=config,
            )
            return response.text or ""
        except Exception as e:
            raise AIFeedbackError(f"Gemini audio request failed: {e}")

    def _generate_text_only(
        self,
        prompt: str,
        generation_config: GenerationConfig,
    ) -> str:
        """Generate text-only response."""
        try:
            config_kwargs: dict[str, Any] = {
                "max_output_tokens": generation_config.max_output_tokens,
                "response_mime_type": "application/json",
            }
            if generation_config.temperature is not None:
                config_kwargs["temperature"] = generation_config.temperature

            response = self.client.models.generate_content(
                model=self.model_id,
                contents=prompt,
                config=types.GenerateContentConfig(**config_kwargs),
            )
            return response.text or ""
        except Exception as e:
            raise AIFeedbackError(str(e))
