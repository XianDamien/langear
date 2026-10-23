from functools import lru_cache
from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CORE_", extra="ignore")
    dialogue_enabled: bool = False
    dialogue_agent_url: str = "http://127.0.0.1:8111"
    dialogue_agent_token: SecretStr | None = None
    dialogue_api_key: SecretStr | None = None
    dialogue_model: str = "qwen3.8-omni-flash-realtime"
    dialogue_ws_url: str = "wss://dashscope.aliyuncs.com/api-ws/v1/realtime"
    dialogue_asr_model: str = "qwen3-asr-flash-realtime"
    dialogue_voice: str = "Tina"
    database_url: str
    confirmation_secret: str
    allowed_origins: list[str] = [
        "http://localhost:3002",
        "http://127.0.0.1:3002",
        "https://8.159.139.145:7145",
    ]
    # The deployment env keeps the historical unprefixed provider/OSS keys.
    # CORE_-prefixed names win when both are present.
    oss_access_key_id: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_OSS_ACCESS_KEY_ID", "OSS_ACCESS_KEY_ID"),
    )
    oss_access_key_secret: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_OSS_ACCESS_KEY_SECRET", "OSS_ACCESS_KEY_SECRET"),
    )
    oss_endpoint: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_OSS_ENDPOINT", "OSS_ENDPOINT"),
    )
    oss_bucket_name: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_OSS_BUCKET_NAME", "OSS_BUCKET_NAME"),
    )
    upload_prefix: str = Field(
        default="dev/staging/review",
        validation_alias=AliasChoices("CORE_UPLOAD_PREFIX", "OSS_RECORDINGS_PREFIX"),
    )
    cookie_secure: bool = True
    session_absolute_seconds: int = 604800
    session_idle_seconds: int = 86400
    confirmation_seconds: int = 600
    auth_limit: int = 20
    invitation_required: bool = False
    dashboard_heatmap_days: int = 90
    dashboard_trend_days: int = 7
    asr_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_ASR_API_KEY", "DASHSCOPE_API_KEY"),
    )
    ai_feedback_provider: str = Field(
        default="gemini",
        validation_alias=AliasChoices("CORE_AI_FEEDBACK_PROVIDER", "AI_FEEDBACK_PROVIDER"),
    )
    ai_feedback_prompt_version: str = Field(
        default="v1",
        validation_alias=AliasChoices(
            "CORE_AI_FEEDBACK_PROMPT_VERSION",
            "AI_FEEDBACK_PROMPT_VERSION",
            "GEMINI_PROMPT_VERSION",
        ),
    )
    gemini_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_GEMINI_API_KEY", "GEMINI_API_KEY"),
    )
    gemini_model_id: str = Field(
        default="gemini-3.8-flash",
        validation_alias=AliasChoices("CORE_GEMINI_MODEL_ID", "GEMINI_MODEL_ID"),
    )
    # The relay endpoint is configured without the CORE_ prefix in deployments.
    gemini_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_GEMINI_BASE_URL", "GOOGLE_GEMINI_BASE_URL"),
    )
    # google-genai expects milliseconds; an unbounded request blocks the outbox worker.
    gemini_request_timeout_ms: int = Field(
        default=180_000,
        gt=0,
        validation_alias=AliasChoices(
            "CORE_GEMINI_REQUEST_TIMEOUT_MS", "GEMINI_REQUEST_TIMEOUT_MS"
        ),
    )
    # The relay currently allows about five concurrent Gemini requests.
    review_worker_concurrency: int = Field(
        default=5,
        ge=1,
        le=32,
        validation_alias=AliasChoices(
            "CORE_REVIEW_WORKER_CONCURRENCY", "REVIEW_WORKER_CONCURRENCY"
        ),
    )
    qwen_omni_api_key: SecretStr | None = Field(
        default=None,
        validation_alias=AliasChoices("CORE_QWEN_OMNI_API_KEY", "QWEN_OMNI_API_KEY"),
    )
    qwen_omni_model_id: str = Field(
        default="qwen3.8-omni-flash",
        validation_alias=AliasChoices("CORE_QWEN_OMNI_MODEL_ID", "QWEN_OMNI_MODEL_ID"),
    )
    qwen_omni_base_url: str = Field(
        default="https://dashscope.aliyuncs.com/compatible-mode/v1",
        validation_alias=AliasChoices("CORE_QWEN_OMNI_BASE_URL", "QWEN_OMNI_BASE_URL"),
    )
    realtime_asr_provider: str = Field(
        default="dashscope",
        validation_alias=AliasChoices("CORE_REALTIME_ASR_PROVIDER", "REALTIME_ASR_PROVIDER"),
    )
    realtime_asr_model: str = Field(
        default="qwen3-asr-flash-realtime",
        validation_alias=AliasChoices("CORE_REALTIME_ASR_MODEL", "REALTIME_ASR_MODEL"),
    )
    realtime_asr_language: str = Field(
        default="en",
        validation_alias=AliasChoices("CORE_REALTIME_ASR_LANGUAGE", "REALTIME_ASR_LANGUAGE"),
    )
    realtime_asr_ws_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "CORE_REALTIME_ASR_WS_BASE_URL", "REALTIME_ASR_WS_BASE_URL"
        ),
    )

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value):
        if not value.startswith("postgresql+psycopg://"):
            raise ValueError("Core requires PostgreSQL with psycopg")
        return value

    @field_validator("confirmation_secret")
    @classmethod
    def strong_secret(cls, value):
        if len(value) < 32:
            raise ValueError("Confirmation secret must be at least 32 characters")
        return value

    @field_validator("allowed_origins")
    @classmethod
    def explicit_origins(cls, values):
        if not values or "*" in values:
            raise ValueError("Explicit credentialed origins are required")
        return values


@lru_cache
def get_settings():
    return Settings()
