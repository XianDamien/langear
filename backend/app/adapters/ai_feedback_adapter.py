"""AI feedback provider abstraction and factory."""

from typing import Any, Protocol

from app.config import settings
from app.exceptions import AIFeedbackError


class AIFeedbackProvider(Protocol):
    """Protocol for pluggable AI feedback providers."""

    def generate_single_feedback(
        self,
        front_text: str,
        user_audio_url: str,
        reference_audio_url: str,
    ) -> dict[str, Any]:
        """Generate feedback for one sentence using user/reference audio."""

    def generate_lesson_summary(self, feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate lesson-level summary from sentence-level feedbacks."""


def create_ai_feedback_provider() -> AIFeedbackProvider:
    """Create provider instance from configuration."""
    provider = settings.ai_feedback_provider.strip().lower()

    if provider == "gemini":
        from app.adapters.gemini_adapter import GeminiAdapter

        return GeminiAdapter()

    raise AIFeedbackError(f"Unsupported AI_FEEDBACK_PROVIDER: {provider}")
