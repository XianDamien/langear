"""DashScope realtime ASR bridge adapter."""

from __future__ import annotations

import asyncio
from typing import Any

from dashscope.audio.qwen_omni.omni_realtime import (
    MultiModality,
    OmniRealtimeCallback,
    OmniRealtimeConversation,
    TranscriptionParams,
)


class DashScopeRealtimeCallback(OmniRealtimeCallback):
    """Forward DashScope callback events into an asyncio queue."""

    def __init__(self, loop: asyncio.AbstractEventLoop, event_queue: asyncio.Queue[dict[str, Any]]):
        self._loop = loop
        self._event_queue = event_queue

    def _push(self, payload: dict[str, Any]) -> None:
        self._loop.call_soon_threadsafe(self._event_queue.put_nowait, payload)

    def on_open(self) -> None:
        self._push({"type": "__internal.connection.open"})

    def on_event(self, message: dict[str, Any]) -> None:
        self._push({"type": "__internal.dashscope.event", "message": message})

    def on_close(self, close_status_code, close_msg) -> None:
        self._push(
            {
                "type": "__internal.connection.close",
                "code": close_status_code,
                "reason": close_msg,
            }
        )


class DashScopeRealtimeASRBridge:
    """Bridge wrapper around DashScope omni realtime conversation."""

    def __init__(
        self,
        api_key: str,
        model: str,
        language: str = "zh",
        sample_rate: int = 16000,
        ws_base_url: str | None = None,
    ):
        self.api_key = api_key
        self.model = model
        self.language = language
        self.sample_rate = sample_rate
        self.ws_base_url = ws_base_url
        self._conversation: OmniRealtimeConversation | None = None

    def connect(
        self,
        loop: asyncio.AbstractEventLoop,
        event_queue: asyncio.Queue[dict[str, Any]],
    ) -> None:
        """Connect to DashScope realtime WS and initialize transcription session."""
        callback = DashScopeRealtimeCallback(loop, event_queue)
        self._conversation = OmniRealtimeConversation(
            model=self.model,
            callback=callback,
            url=self.ws_base_url,
            api_key=self.api_key,
        )
        self._conversation.connect()
        self._conversation.update_session(
            output_modalities=[MultiModality.TEXT],
            enable_turn_detection=False,
            transcription_params=TranscriptionParams(
                language=self.language,
                sample_rate=self.sample_rate,
                input_audio_format="pcm",
            ),
        )

    def append_audio(self, audio_base64: str) -> None:
        """Append pcm16 audio chunk."""
        if self._conversation is None:
            raise RuntimeError("DashScope conversation is not connected")
        self._conversation.append_audio(audio_base64)

    def commit(self) -> None:
        """Commit audio buffer."""
        if self._conversation is None:
            raise RuntimeError("DashScope conversation is not connected")
        self._conversation.commit()

    def close(self) -> None:
        """Close conversation."""
        if self._conversation is None:
            return
        self._conversation.close()
