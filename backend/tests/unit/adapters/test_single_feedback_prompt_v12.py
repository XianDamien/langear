from pathlib import Path

from app.adapters.ai_feedback_adapter import create_ai_feedback_provider


def test_single_feedback_prompt_requires_conservative_stress_judgments(monkeypatch):
    monkeypatch.setenv("AI_FEEDBACK_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL_ID", "gemini-3.8-flash")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "https://example.test")

    prompt = create_ai_feedback_provider().single_feedback_prompt
    combined = f"{prompt.system}\n{prompt.user}"

    assert "判断重音前必须核实该词的标准词重音" in combined
    assert "接受可理解的标准英语口音变体" in combined
    assert "不要输出单独的问题点" in combined
    assert "issues` 必须始终返回空数组" in combined
    assert "最多 2 条" in combined


def test_prompt_metadata_tracks_conservative_suggestions_revision():
    metadata_path = (
        Path(__file__).parents[3]
        / "app/adapters/prompts/v1/single_feedback/metadata.json"
    )
    import json

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["prompt_version"] == "1.2.0"
    assert metadata["changelog"][0]["version"] == "1.2.0"
