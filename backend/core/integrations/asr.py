"""Alibaba Cloud ASR through DashScope qwen3-asr-flash.

The signed OSS URL is passed straight to the provider; no credential from the
frontend is trusted here.
"""

import dashscope

from core.config import get_settings
from core.integrations.errors import ASRTranscriptionError

MODEL = "qwen3-asr-flash"


def transcribe(audio_url: str) -> dict:
    settings = get_settings()
    if not settings.asr_api_key:
        raise ASRTranscriptionError("ASR is not configured")
    dashscope.api_key = settings.asr_api_key.get_secret_value()
    try:
        response = dashscope.MultiModalConversation.call(
            model=settings.asr_model or MODEL,
            messages=[{"role": "user", "content": [{"audio": audio_url}]}],
            asr_options={"enable_itn": False},
        )
    except Exception:
        # Provider exceptions can embed the signed URL; keep the cause opaque.
        raise ASRTranscriptionError("ASR transcription failed") from None
    if response.status_code != 200:
        raise ASRTranscriptionError(
            f"ASR API returned status {response.status_code}"
        )
    text = extract_text(response.output).strip()
    if not text:
        raise ASRTranscriptionError("No transcription in response")
    return {"text": text, "timestamps": extract_timestamps(response.output)}


def extract_text(output) -> str:
    """Read both the multimodal and legacy response shapes."""
    if not isinstance(output, dict):
        return ""
    choices = output.get("choices")
    if isinstance(choices, list):
        parts = []
        for choice in choices:
            message = choice.get("message") if isinstance(choice, dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
        if parts:
            return " ".join(parts)
    results = output.get("results")
    if isinstance(results, list) and results and isinstance(results[0], dict):
        text = results[0].get("transcription_text")
        if isinstance(text, str):
            return text
    text = output.get("text")
    return text if isinstance(text, str) else ""


def extract_timestamps(output) -> list:
    """Keep legacy word timings when the provider returns them."""
    results = output.get("results") if isinstance(output, dict) else None
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        return []
    sentences = results[0].get("sentence")
    if not isinstance(sentences, list):
        return []
    timestamps = []
    for sentence in sentences:
        words = sentence.get("words") if isinstance(sentence, dict) else None
        if not isinstance(words, list):
            continue
        for word in words:
            if not isinstance(word, dict):
                continue
            timestamps.append(
                {
                    "word": word.get("text", ""),
                    "start": word.get("begin_time", 0) / 1000.0,
                    "end": word.get("end_time", 0) / 1000.0,
                }
            )
    return timestamps
