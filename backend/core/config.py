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
    oss_access_key_id: SecretStr | None = None
    oss_access_key_secret: SecretStr | None = None
    oss_endpoint: str | None = None
    oss_bucket_name: str | None = None
    upload_prefix: str = "dev/staging/review"
    legacy_identity_url: str | None = None
    legacy_import_source: str | None = None
    cookie_secure: bool = True
    session_absolute_seconds: int = 604800
    session_idle_seconds: int = 86400
    confirmation_seconds: int = 600
    auth_limit: int = 20
    invitation_required: bool = False
    dashboard_heatmap_days: int = 90
    dashboard_trend_days: int = 7
    asr_api_key: SecretStr | None = None
    ai_feedback_provider: str = "gemini"
    ai_feedback_prompt_version: str = "v1"
    gemini_api_key: SecretStr | None = None
    gemini_model_id: str = "gemini-3.1-flash-lite-preview"
    # The deployment environment configures the relay without the CORE_ prefix.
    gemini_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_GEMINI_BASE_URL", "CORE_GEMINI_BASE_URL"),
    )
    qwen_omni_api_key: SecretStr | None = None
    qwen_omni_model_id: str = "qwen3.8-omni-flash"
    qwen_omni_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    realtime_asr_provider: str = "dashscope"
    realtime_asr_model: str = "qwen3-asr-flash-realtime"
    realtime_asr_language: str = "zh"
    realtime_asr_ws_base_url: str | None = None

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
