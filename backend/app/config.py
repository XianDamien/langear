"""Application configuration using Pydantic Settings."""

from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.database_url import build_default_sqlite_database_url, resolve_database_url


BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASE_URL = build_default_sqlite_database_url(BACKEND_ROOT)
DEFAULT_CORS_ORIGINS = "http://localhost:3002,http://127.0.0.1:3002"


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = DEFAULT_DATABASE_URL

    # Local token auth
    auth_token_secret: str | None = None

    # Business timezone
    app_timezone: str = "Asia/Shanghai"

    # Google Gemini API
    gemini_api_key: str
    gemini_model_id: str = "gemini-3.1-flash-lite-preview"
    gemini_prompt_version: str = "v1"
    google_gemini_base_url: str | None = None

    # AI feedback provider
    ai_feedback_provider: str = "gemini"

    # Coach / Q&A Agent
    coach_agent_model_id: str | None = None
    coach_agent_api_key: str | None = None
    coach_agent_app_name: str = "langear-coach"
    coach_kb_dir: str = str(BACKEND_ROOT / "knowledge_base")
    coach_session_db_path: str = str(BACKEND_ROOT / "data" / "coach_sessions.db")
    coach_history_limit: int = 5
    coach_kb_top_k: int = 3

    # Alibaba Cloud OSS
    oss_access_key_id: str
    oss_access_key_secret: str
    oss_endpoint: str
    oss_bucket_name: str
    oss_recordings_prefix: str = "recordings"
    # Optional legacy base URL for public-read objects. The app now defaults to
    # STS upload + signed URL access, so this is no longer required.
    oss_public_base_url: str | None = None
    # NOTE:
    # - STS client region id usually looks like: "cn-shanghai"
    # - OSS bucket region usually looks like: "oss-cn-shanghai"
    # We keep a single env var for simplicity and normalize where needed.
    oss_region: str | None = "cn-shanghai"

    # Alibaba Cloud STS (for temporary credentials)
    aliyun_role_arn: str | None = None  # RAM role ARN for AssumeRole

    # Alibaba Cloud ASR (DashScope)
    dashscope_api_key: str
    # "dashscope" uses real DashScope realtime ASR, "mock" keeps in-process fake stream.
    realtime_asr_provider: str = "dashscope"
    realtime_asr_model: str = "qwen3-asr-flash-realtime"
    realtime_asr_language: str = "zh"
    # Optional custom websocket endpoint for region-specific deployment.
    # Example: wss://dashscope.aliyuncs.com/api-ws/v1/realtime
    realtime_asr_ws_base_url: str | None = None

    # CORS
    cors_origins: str = DEFAULT_CORS_ORIGINS

    @property
    def resolved_database_url(self) -> str:
        """Return the runtime database URL with sqlite paths normalized."""
        return resolve_database_url(self.database_url, base_dir=BACKEND_ROOT)

    @property
    def sqlite_database_path(self) -> Path | None:
        """Return the resolved sqlite file path when DATABASE_URL uses sqlite."""
        url = make_url(self.resolved_database_url)
        if url.drivername != "sqlite" or not url.database or url.database == ":memory:":
            return None
        return Path(url.database).resolve()

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_ai_feedback_settings(self) -> "Settings":
        """Validate provider-specific AI feedback settings."""
        self.database_url = self.resolved_database_url
        self.app_timezone = "Asia/Shanghai"
        self.google_gemini_base_url = (
            self.google_gemini_base_url.strip()
            if self.google_gemini_base_url and self.google_gemini_base_url.strip()
            else None
        )
        self.coach_agent_api_key = (
            self.coach_agent_api_key.strip()
            if self.coach_agent_api_key and self.coach_agent_api_key.strip()
            else None
        )
        self.coach_agent_model_id = (
            self.coach_agent_model_id.strip()
            if self.coach_agent_model_id and self.coach_agent_model_id.strip()
            else None
        )
        provider = self.ai_feedback_provider.strip().lower()
        if provider == "gemini" and not self.gemini_model_id.strip():
            raise ValueError(
                "GEMINI_MODEL_ID is required when AI_FEEDBACK_PROVIDER is 'gemini'"
            )
        return self


# Global settings instance
settings = Settings()
