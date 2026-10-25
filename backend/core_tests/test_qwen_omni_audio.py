"""Audio reaches providers as signed URLs; no base64 copy is built locally."""

import pytest

from core.config import get_settings
from core.integrations.feedback import GenerationConfig
from core.integrations.qwen_omni import QwenOmniProvider

SIGNED = (
    "https://langear.oss-cn-shanghai.aliyuncs.com/recordings/a.webm"
    "?Expires=1&OSSAccessKeyId=id&Signature=x"
)


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("CORE_QWEN_OMNI_API_KEY", "secret-test-key")
    monkeypatch.setenv("CORE_QWEN_OMNI_BASE_URL", "https://dashscope.example/v1")
    monkeypatch.setenv("CORE_QWEN_OMNI_MODEL_ID", "qwen-omni-test")
    get_settings.cache_clear()
    yield QwenOmniProvider()
    get_settings.cache_clear()


def test_signed_url_is_sent_verbatim_without_base64(provider):
    part = provider._audio_part(SIGNED)
    assert part == {
        "type": "input_audio",
        "input_audio": {"data": SIGNED, "format": "webm"},
    }


def test_both_audio_parts_keep_their_signed_urls(provider, monkeypatch):
    captured = {}

    def capture(content, generation_config):
        captured["content"] = content
        return "{}"

    monkeypatch.setattr(provider, "_request", capture)
    provider._generate_with_audio(
        "prompt",
        "https://oss.example/user.webm?Signature=u",
        "https://oss.example/ref.mp3?Signature=r",
        GenerationConfig(),
    )

    audios = [item for item in captured["content"] if item["type"] == "input_audio"]
    assert [item["input_audio"]["data"] for item in audios] == [
        "https://oss.example/ref.mp3?Signature=r",
        "https://oss.example/user.webm?Signature=u",
    ]
    assert all("base64" not in str(item) for item in audios)
