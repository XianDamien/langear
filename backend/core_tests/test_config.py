from core.config import Settings


def test_deployment_env_accepts_unprefixed_provider_keys(monkeypatch):
    monkeypatch.setenv("CORE_DATABASE_URL", "postgresql+psycopg://test@localhost/test")
    monkeypatch.setenv("CORE_CONFIRMATION_SECRET", "a" * 32)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key")
    monkeypatch.setenv("REALTIME_ASR_PROVIDER", "dashscope")
    monkeypatch.setenv("REALTIME_ASR_MODEL", "qwen3-asr-flash-realtime")
    monkeypatch.setenv("REALTIME_ASR_LANGUAGE", "zh")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")
    monkeypatch.setenv("GEMINI_MODEL_ID", "gem-model")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://relay.example")
    monkeypatch.setenv("AI_FEEDBACK_PROVIDER", "gemini")
    monkeypatch.setenv("AI_FEEDBACK_PROMPT_VERSION", "v2")
    monkeypatch.setenv("OSS_ACCESS_KEY_ID", "oss-id")
    monkeypatch.setenv("OSS_ACCESS_KEY_SECRET", "oss-secret")
    monkeypatch.setenv("OSS_ENDPOINT", "oss-endpoint")
    monkeypatch.setenv("OSS_BUCKET_NAME", "oss-bucket")
    monkeypatch.setenv("OSS_RECORDINGS_PREFIX", "recordings")
    monkeypatch.setenv("QWEN_OMNI_API_KEY", "qwen-key")

    settings = Settings(_env_file=None)

    assert settings.asr_api_key.get_secret_value() == "dash-key"
    assert settings.realtime_asr_model == "qwen3-asr-flash-realtime"
    assert settings.gemini_api_key.get_secret_value() == "gem-key"
    assert settings.gemini_model_id == "gem-model"
    assert settings.gemini_base_url == "https://relay.example"
    assert settings.ai_feedback_prompt_version == "v2"
    assert settings.oss_access_key_id.get_secret_value() == "oss-id"
    assert settings.oss_bucket_name == "oss-bucket"
    assert settings.upload_prefix == "recordings"
    assert settings.qwen_omni_api_key.get_secret_value() == "qwen-key"


def test_core_prefixed_keys_take_precedence(monkeypatch):
    monkeypatch.setenv("CORE_DATABASE_URL", "postgresql+psycopg://test@localhost/test")
    monkeypatch.setenv("CORE_CONFIRMATION_SECRET", "a" * 32)
    monkeypatch.setenv("CORE_ASR_API_KEY", "core-key")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "dash-key")
    monkeypatch.setenv("CORE_GEMINI_API_KEY", "core-gem")
    monkeypatch.setenv("GEMINI_API_KEY", "gem-key")

    settings = Settings(_env_file=None)

    assert settings.asr_api_key.get_secret_value() == "core-key"
    assert settings.gemini_api_key.get_secret_value() == "core-gem"
