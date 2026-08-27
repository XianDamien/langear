"""Google Gemini adapter for AI evaluation."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

from google import genai
from google.genai import types

from app.config import settings
from app.exceptions import AIFeedbackError


@dataclass(frozen=True)
class PromptTemplate:
    """Structured prompt template split into system and user sections."""

    system: str
    user: str
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class GenerationConfig:
    """Generation controls used for production and offline eval runs."""

    temperature: float | None = None
    max_output_tokens: int = 2048


class GeminiAdapter:
    """Adapter for Google Gemini AI multimodal evaluation."""

    def __init__(self):
        """Initialize Gemini client, model, and prompt templates."""
        api_key = settings.gemini_api_key.strip()
        if not api_key:
            raise AIFeedbackError("Missing Gemini API key")

        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if settings.google_gemini_base_url:
            client_kwargs["http_options"] = types.HttpOptions(
                base_url=settings.google_gemini_base_url
            )

        self.client = genai.Client(**client_kwargs)
        self.model_id = settings.gemini_model_id.strip()
        self.prompts_dir = Path(__file__).parent / "prompts" / settings.gemini_prompt_version

        self.single_feedback_prompt = self._load_prompt("single_feedback")
        self.lesson_summary_prompt = self._load_prompt("lesson_summary")

    @staticmethod
    def _read_prompt_file(path: Path) -> str:
        """Read a required prompt file and validate it is non-empty."""
        if not path.exists():
            raise AIFeedbackError(f"Prompt file not found: {path}")

        content = path.read_text(encoding="utf-8").strip()
        if not content:
            raise AIFeedbackError(f"Prompt file is empty: {path}")
        return content

    def _load_prompt(self, prompt_name: str) -> PromptTemplate:
        """Load structured prompt template from versioned prompt directory."""
        prompt_dir = self.prompts_dir / prompt_name
        return self.load_prompt_from_dir(prompt_dir)

    def load_prompt_from_dir(self, prompt_dir: str | Path) -> PromptTemplate:
        """Load structured prompt template from an arbitrary prompt directory."""
        prompt_dir = Path(prompt_dir)
        if not prompt_dir.is_dir():
            raise AIFeedbackError(f"Prompt directory not found: {prompt_dir}")

        metadata: dict[str, Any] | None = None
        metadata_file = prompt_dir / "metadata.json"
        if metadata_file.exists():
            try:
                metadata = json.loads(self._read_prompt_file(metadata_file))
            except json.JSONDecodeError as e:
                raise AIFeedbackError(
                    f"Prompt metadata is invalid JSON: {metadata_file}, error={e}"
                )

        return PromptTemplate(
            system=self._read_prompt_file(prompt_dir / "system.md"),
            user=self._read_prompt_file(prompt_dir / "user.md"),
            metadata=metadata,
        )

    @staticmethod
    def _render_prompt(template: str, **variables: Any) -> str:
        """Render placeholders without interpreting JSON braces in templates."""
        rendered = template
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    def _render_prompt_template(
        self,
        template: PromptTemplate,
        **variables: Any,
    ) -> str:
        """Render structured prompt sections into one request string."""
        system_prompt = self._render_prompt(template.system, **variables)
        user_prompt = self._render_prompt(template.user, **variables)
        return f"{system_prompt}\n\n{user_prompt}".strip()

    @staticmethod
    def _extract_json_text(raw_text: str) -> str:
        """Extract JSON payload from model output text."""
        result_text = raw_text.strip()

        if result_text.startswith("```"):
            parts = result_text.split("```")
            if len(parts) >= 2:
                result_text = parts[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
            result_text = result_text.strip()

        return result_text

    @staticmethod
    def _download_audio_bytes(audio_url: str, timeout: int = 30) -> bytes:
        """Download audio bytes for the single official SDK request path."""
        try:
            with urlopen(audio_url, timeout=timeout) as response:
                data = response.read()
                if not data:
                    raise AIFeedbackError(f"Empty audio content: {audio_url}")
                return data
        except AIFeedbackError:
            raise
        except Exception as e:
            raise AIFeedbackError(f"Failed to download audio: {audio_url}, error={e}")

    @staticmethod
    def _guess_audio_mime_type(audio_url: str) -> str:
        """Best-effort MIME type inference by URL suffix."""
        path = urlparse(audio_url).path.lower()
        if path.endswith(".wav"):
            return "audio/wav"
        if path.endswith(".webm"):
            return "audio/webm"
        if path.endswith(".mp3"):
            return "audio/mpeg"
        if path.endswith(".m4a"):
            return "audio/mp4"
        if path.endswith(".ogg"):
            return "audio/ogg"
        return "application/octet-stream"

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

    @staticmethod
    def _normalize_suggestions(raw: Any) -> list[dict[str, Any]]:
        """Normalize suggestions to a stable list-of-objects schema."""
        if not isinstance(raw, list):
            raise AIFeedbackError("Field 'suggestions' must be a list")

        normalized: list[dict[str, Any]] = []
        for item in raw:
            if isinstance(item, str):
                normalized.append(
                    {"text": item, "target_word": None, "timestamp": None}
                )
                continue

            if not isinstance(item, dict):
                raise AIFeedbackError("Each suggestion must be an object or string")

            text = item.get("text")
            if not isinstance(text, str) or not text.strip():
                raise AIFeedbackError("Each suggestion requires a non-empty 'text'")

            target_word = item.get("target_word")
            if target_word is not None and not isinstance(target_word, str):
                raise AIFeedbackError("suggestion.target_word must be a string or null")

            timestamp = item.get("timestamp")
            if timestamp is not None and not isinstance(timestamp, (int, float)):
                raise AIFeedbackError("suggestion.timestamp must be a number or null")

            normalized.append(
                {
                    "text": text.strip(),
                    "target_word": target_word,
                    "timestamp": float(timestamp) if timestamp is not None else None,
                }
            )

        return normalized

    @staticmethod
    def _normalize_issues(raw: Any) -> list[dict[str, Any]]:
        """Normalize issues to [{problem, timestamp}] format."""
        if not isinstance(raw, list):
            raise AIFeedbackError("Field 'issues' must be a list")

        normalized: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise AIFeedbackError("Each issue must be an object")

            problem = item.get("problem")
            if not isinstance(problem, str) or not problem.strip():
                raise AIFeedbackError("Each issue requires a non-empty 'problem'")

            timestamp = item.get("timestamp")
            if timestamp is not None and not isinstance(timestamp, (int, float)):
                raise AIFeedbackError("issue.timestamp must be a number or null")

            normalized.append(
                {
                    "problem": problem.strip(),
                    "timestamp": float(timestamp) if timestamp is not None else None,
                }
            )

        return normalized

    def generate_single_feedback(
        self,
        front_text: str,
        user_audio_url: str,
        reference_audio_url: str,
        prompt_template: PromptTemplate | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> dict[str, Any]:
        """Generate single-sentence feedback from user/reference audio."""
        try:
            prompt_template = prompt_template or self.single_feedback_prompt
            generation_config = generation_config or GenerationConfig()
            prompt = self._render_prompt_template(
                prompt_template,
                original_text=front_text,
                user_audio_url=user_audio_url,
                reference_audio_url=reference_audio_url,
            )

            result_text = self._generate_with_audio(
                prompt=prompt,
                user_audio_url=user_audio_url,
                reference_audio_url=reference_audio_url,
                generation_config=generation_config,
            )
            feedback = json.loads(self._extract_json_text(result_text))

            required_fields = [
                "transcription_text",
                "pronunciation",
                "completeness",
                "fluency",
                "suggestions",
                "issues",
            ]
            for field in required_fields:
                if field not in feedback:
                    raise AIFeedbackError(f"Missing required field: {field}")

            for field in ("pronunciation", "completeness", "fluency"):
                if not isinstance(feedback[field], str):
                    raise AIFeedbackError(f"Field '{field}' must be a string")

            normalized_feedback = {
                "transcription_text": "",
                "pronunciation": feedback["pronunciation"].strip(),
                "completeness": feedback["completeness"].strip(),
                "fluency": feedback["fluency"].strip(),
                "suggestions": self._normalize_suggestions(feedback["suggestions"]),
                "issues": self._normalize_issues(feedback["issues"]),
            }

            if not isinstance(feedback["transcription_text"], str):
                raise AIFeedbackError("Field 'transcription_text' must be a string")
            normalized_feedback["transcription_text"] = feedback[
                "transcription_text"
            ].strip()

            return normalized_feedback

        except json.JSONDecodeError as e:
            raise AIFeedbackError(f"Failed to parse JSON response: {e}")
        except AIFeedbackError:
            raise
        except Exception as e:
            raise AIFeedbackError(str(e))

    def generate_lesson_summary(
        self,
        feedbacks: list[dict[str, Any]],
        prompt_template: PromptTemplate | None = None,
        generation_config: GenerationConfig | None = None,
    ) -> dict[str, Any]:
        """Generate lesson-level summary from all feedback."""
        try:
            prompt_template = prompt_template or self.lesson_summary_prompt
            generation_config = generation_config or GenerationConfig()
            feedbacks_json = json.dumps(feedbacks, ensure_ascii=False, indent=2)
            prompt = self._render_prompt_template(
                prompt_template,
                feedbacks_json=feedbacks_json,
            )

            result_text = self._generate_text_only(
                prompt,
                generation_config=generation_config,
            )
            summary = json.loads(self._extract_json_text(result_text))

            required_fields = ["overall", "patterns", "prioritized_actions"]
            for field in required_fields:
                if field not in summary:
                    raise AIFeedbackError(f"Missing required field: {field}")

            if not isinstance(summary["overall"], str):
                raise AIFeedbackError("Field 'overall' must be a string")
            if not isinstance(summary["patterns"], list):
                raise AIFeedbackError("Field 'patterns' must be a list")
            if not isinstance(summary["prioritized_actions"], list):
                raise AIFeedbackError("Field 'prioritized_actions' must be a list")

            return summary

        except json.JSONDecodeError as e:
            raise AIFeedbackError(f"Failed to parse JSON response: {e}")
        except AIFeedbackError:
            raise
        except Exception as e:
            raise AIFeedbackError(str(e))
