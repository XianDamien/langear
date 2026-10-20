from pathlib import Path

from app.adapters.ai_feedback_adapter import create_ai_feedback_provider
from app.adapters.feedback_base import FeedbackAdapterBase


def test_prompt_requires_dimension_tagged_suggestions(monkeypatch):
    monkeypatch.setenv("AI_FEEDBACK_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-3.8-flash")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://example.test")

    prompt = create_ai_feedback_provider().single_feedback_prompt
    combined = f"{prompt.system}\n{prompt.user}"

    # Three-dimension evaluation stays a required output, one sentence each.
    assert "三个评价字段只描述各自维度" in combined
    assert "必须各给出一句话评价" in combined
    # Every suggestion must declare which dimension it improves.
    assert "`dimension`" in combined
    assert "pronunciation`、`completeness`、`fluency` 之一" in combined
    # The empty-issues contract and the conservative suggestion cap must survive.
    assert "issues` 必须始终返回空数组" in combined
    assert "最多 2 条" in combined
    # The JSON schema example must not invite problem entries back.
    assert '"issues": []' in combined


def test_prompt_metadata_tracks_dimension_revision():
    metadata_path = (
        Path(__file__).parents[3]
        / "app/adapters/prompts/v1/single_feedback/metadata.json"
    )
    import json

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["prompt_version"] == "1.3.0"
    assert metadata["changelog"][0]["version"] == "1.3.0"


def test_normalize_suggestions_maps_dimension_and_degrades_unknown_values():
    normalized = FeedbackAdapterBase._normalize_suggestions(
        [
            {"text": "练习 /eə/ 的滑动。", "dimension": "pronunciation", "timestamp": 1.2},
            {"text": "注意句尾吞音。", "dimension": "发音"},
            {"text": "补上关键信息。", "dimension": "completeness"},
            {"text": "放慢语速。", "dimension": "语速"},
            "旧格式建议",
        ]
    )

    assert [item["dimension"] for item in normalized] == [
        "pronunciation",
        "pronunciation",
        "completeness",
        None,
        None,
    ]
    assert normalized[0]["target_word"] is None
