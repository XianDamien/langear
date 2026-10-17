"""Unit tests for configuration validation."""

import pytest

from app.config import BACKEND_ROOT, Settings


@pytest.mark.unit
def test_gemini_model_id_cannot_be_blank_for_gemini_provider():
    with pytest.raises(ValueError) as exc_info:
        Settings(
            _env_file=None,
            database_url="sqlite:///data/langear.db",
            gemini_api_key="test-key",
            gemini_model_id="   ",
            ai_feedback_provider="gemini",
            oss_access_key_id="id",
            oss_access_key_secret="secret",
            oss_endpoint="oss-cn-shanghai.aliyuncs.com",
            oss_bucket_name="bucket",
            aliyun_role_arn="acs:ram::123456789012:role/test",
            dashscope_api_key="dashscope-key",
        )

    assert "GEMINI_MODEL_ID is required" in str(exc_info.value)


@pytest.mark.unit
def test_gemini_settings_use_default_model_id(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_ID", raising=False)
    monkeypatch.delenv("GOOGLE_GEMINI_BASE_URL", raising=False)

    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.gemini_model_id == "gemini-3.1-flash-lite-preview"


@pytest.mark.unit
def test_google_gemini_base_url_is_trimmed():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        gemini_model_id="gemini-3.1-flash-lite-preview",
        google_gemini_base_url="  https://relay.example.com  ",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.google_gemini_base_url == "https://relay.example.com"


@pytest.mark.unit
def test_settings_can_skip_aliyun_role_arn_until_sts_is_used(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_ID", raising=False)

    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn=None,
        dashscope_api_key="dashscope-key",
    )

    assert settings.aliyun_role_arn is None
    assert settings.gemini_model_id == "gemini-3.1-flash-lite-preview"


@pytest.mark.unit
def test_gemini_settings_pass_with_explicit_model_id():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        gemini_model_id="gemini-3.1-flash-lite-preview",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.gemini_model_id == "gemini-3.1-flash-lite-preview"


@pytest.mark.unit
def test_non_gemini_provider_can_skip_gemini_model_id(monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL_ID", raising=False)

    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="mock-provider",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.ai_feedback_provider == "mock-provider"
    assert settings.gemini_model_id == "gemini-3.1-flash-lite-preview"


@pytest.mark.unit
def test_relative_sqlite_database_url_resolves_against_backend_root():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        oss_public_base_url="https://bucket.oss-cn-shanghai.aliyuncs.com",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    expected_path = (BACKEND_ROOT / "data/langear.db").resolve()
    assert settings.database_url == f"sqlite:///{expected_path}"
    assert settings.resolved_database_url == f"sqlite:///{expected_path}"
    assert settings.sqlite_database_path == expected_path


@pytest.mark.unit
def test_cors_origins_default_supports_localhost_and_loopback():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        oss_public_base_url="https://bucket.oss-cn-shanghai.aliyuncs.com",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.cors_origins_list == [
        "http://localhost:3002",
        "http://127.0.0.1:3002",
    ]


@pytest.mark.unit
def test_settings_can_skip_oss_public_base_url():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.oss_public_base_url is None


@pytest.mark.unit
def test_app_timezone_is_forced_to_asia_shanghai():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        app_timezone="Europe/Budapest",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.app_timezone == "Asia/Shanghai"


@pytest.mark.unit
def test_invalid_app_timezone_input_is_ignored():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        app_timezone="Mars/Olympus",
        gemini_api_key="test-key",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        aliyun_role_arn="acs:ram::123456789012:role/test",
        dashscope_api_key="dashscope-key",
    )

    assert settings.app_timezone == "Asia/Shanghai"


@pytest.mark.unit
def test_non_gemini_provider_does_not_require_gemini_credentials(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        ai_feedback_provider="aliyun",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        dashscope_api_key="dashscope-key",
    )

    assert settings.gemini_api_key is None
    assert settings.ai_feedback_prompt_version == "v1"


@pytest.mark.unit
def test_gemini_prompt_version_remains_a_legacy_alias():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        gemini_prompt_version="  v2  ",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        dashscope_api_key="dashscope-key",
    )

    assert settings.ai_feedback_prompt_version == "v2"


@pytest.mark.unit
def test_shared_prompt_version_takes_precedence_over_legacy_alias():
    settings = Settings(
        _env_file=None,
        database_url="sqlite:///data/langear.db",
        gemini_api_key="test-key",
        gemini_prompt_version="v1",
        ai_feedback_prompt_version="v3",
        ai_feedback_provider="gemini",
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        dashscope_api_key="dashscope-key",
    )

    assert settings.ai_feedback_prompt_version == "v3"


@pytest.mark.parametrize("key,model,expected_error", [
    (None, "qwen3.8-omni-flash", "QWEN_OMNI_API_KEY is required"),
    ("test-key", "  ", "QWEN_OMNI_MODEL_ID is required"),
    ("test-key", "qwen3.8-omni-flash", None),
])
def test_qwen_settings_validate_independently_of_gemini(key, model, expected_error):
    values = dict(
        _env_file=None,
        database_url="sqlite:///:memory:",
        ai_feedback_provider="qwen_omni",
        gemini_api_key=None,
        qwen_omni_api_key=key,
        qwen_omni_model_id=model,
        oss_access_key_id="id",
        oss_access_key_secret="secret",
        oss_endpoint="oss-cn-shanghai.aliyuncs.com",
        oss_bucket_name="bucket",
        dashscope_api_key="unchanged-asr-key",
    )
    if expected_error:
        with pytest.raises(ValueError, match=expected_error):
            Settings(**values)
    else:
        config = Settings(**values)
        assert config.gemini_api_key is None
        assert config.dashscope_api_key == "unchanged-asr-key"
