"""Provider-neutral AI feedback contracts and provider factory."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from app.config import settings
from app.exceptions import AIFeedbackError


@dataclass(frozen=True)
class PromptTemplate:
    """Provider-neutral prompt sections loaded from a versioned prompt directory."""

    system: str
    user: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class GenerationConfig:
    """Provider-neutral generation controls mapped by each provider adapter."""

    temperature: float | None = None
    max_output_tokens: int = 2048


class AIFeedbackProvider(Protocol):
    """Contract shared by production feedback and offline prompt evaluation."""

    provider_id: str
    model_id: str

    def load_prompt_from_dir(self, prompt_dir: str | Path) -> PromptTemplate:
        """Load a prompt directory using the shared prompt file contract."""

    def generate_single_feedback(
        self,
        front_text: str,
        user_audio_url: str,
        reference_audio_url: str,
        prompt_template: PromptTemplate | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> dict[str, Any]:
        """Generate feedback for one sentence using user/reference audio."""

    def generate_lesson_summary(self, feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
        """Generate lesson-level summary from sentence-level feedbacks."""


ProviderFactory = Callable[[], AIFeedbackProvider]


def _create_gemini_provider() -> AIFeedbackProvider:
    from app.adapters.gemini_adapter import GeminiAdapter

    return GeminiAdapter()


def _create_qwen_omni_provider() -> AIFeedbackProvider:
    from app.adapters.qwen_omni_adapter import QwenOmniAdapter

    return QwenOmniAdapter()


_PROVIDER_FACTORIES: dict[str, ProviderFactory] = {
    "gemini": _create_gemini_provider,
    "qwen_omni": _create_qwen_omni_provider,
}


def registered_ai_feedback_providers() -> tuple[str, ...]:
    """Return provider ids currently available to the application."""

    return tuple(sorted(_PROVIDER_FACTORIES))


def create_ai_feedback_provider(provider_id: str | None = None) -> AIFeedbackProvider:
    """Create a provider by id, defaulting to the configured runtime provider."""

    selected_provider = (
        settings.ai_feedback_provider if provider_id is None else provider_id
    ).strip().lower()
    factory = _PROVIDER_FACTORIES.get(selected_provider)
    if factory is None:
        supported = ", ".join(registered_ai_feedback_providers())
        raise AIFeedbackError(
            f"Unsupported AI_FEEDBACK_PROVIDER: {selected_provider} "
            f"(supported: {supported})"
        )
    return factory()
