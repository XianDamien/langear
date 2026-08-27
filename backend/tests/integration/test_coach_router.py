"""Integration tests for coach chat endpoints."""

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient


class FakeCoachRuntime:
    """Minimal fake runtime for coach router integration tests."""

    def __init__(self):
        self.threads: dict[tuple[int, str], dict] = {}
        self.counter = 0

    async def stream_chat(
        self,
        *,
        user_id: int,
        lesson_id: int,
        card_id: int | None,
        thread_id: str | None,
        prompt: str,
    ):
        if thread_id is None:
            self.counter += 1
            thread_id = f"thread-{self.counter}"

        key = (user_id, thread_id)
        record = self.threads.setdefault(
            key,
            {
                "thread_id": thread_id,
                "lesson_id": lesson_id,
                "card_id": card_id,
                "messages": [],
                "last_update_time": 0.0,
            },
        )
        record["messages"].append({"author": "user", "content": prompt})
        record["messages"].append({"author": "langear_lesson_coach", "content": "这是答疑结果。"})
        record["last_update_time"] = 12345.0

        yield {"type": "message_delta", "thread_id": thread_id, "delta": "这是答疑结果。"}

    def get_thread(self, *, user_id: int, thread_id: str):
        record = self.threads.get((user_id, thread_id))
        if record is None:
            return None
        return SimpleNamespace(
            thread_id=thread_id,
            user_id=user_id,
            lesson_id=record["lesson_id"],
            card_id=record["card_id"],
            last_update_time=record["last_update_time"],
            message_count=len(record["messages"]),
        )

    def get_thread_messages(self, *, user_id: int, thread_id: str):
        record = self.threads.get((user_id, thread_id))
        if record is None:
            raise ValueError(f"Coach thread {thread_id} not found")
        return record["messages"]


@pytest.mark.integration
class TestCoachRouter:
    """Coach router API tests."""

    def test_chat_stream_includes_answer_and_metadata(
        self,
        client: TestClient,
        sample_card_with_srs,
        sample_review_log_completed,
        monkeypatch,
        tmp_path,
    ):
        lesson = sample_card_with_srs["lesson"]
        card = sample_card_with_srs["card"]
        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        (kb_dir / "qa.md").write_text(
            """---
title: 礼貌表达
tags: [politeness]
---

在餐厅场景中，先用礼貌表达提出请求。
""",
            encoding="utf-8",
        )

        fake_runtime = FakeCoachRuntime()
        monkeypatch.setattr("app.services.coach_service.get_coach_runtime", lambda: fake_runtime)
        monkeypatch.setattr("app.services.coach_kb_service.settings.coach_kb_dir", str(kb_dir))

        response = client.post(
            "/api/v1/coach/chat",
            json={
                "user_id": 1,
                "lesson_id": lesson.id,
                "card_id": card.id,
                "message": "为什么我这里说得不自然？",
            },
        )

        assert response.status_code == 200
        events = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        event_types = [event["type"] for event in events]

        assert "message_delta" in event_types
        assert "citations" in event_types
        assert "jump_targets" in event_types
        assert "resource_links" in event_types
        assert "done" in event_types

    def test_thread_and_messages_can_be_read_back(
        self,
        client: TestClient,
        sample_card_with_srs,
        sample_review_log_completed,
        monkeypatch,
        tmp_path,
    ):
        lesson = sample_card_with_srs["lesson"]
        card = sample_card_with_srs["card"]
        kb_dir = tmp_path / "kb"
        kb_dir.mkdir()
        (kb_dir / "qa.md").write_text("# 练习\n继续练习礼貌表达。", encoding="utf-8")

        fake_runtime = FakeCoachRuntime()
        monkeypatch.setattr("app.services.coach_service.get_coach_runtime", lambda: fake_runtime)
        monkeypatch.setattr("app.services.coach_kb_service.settings.coach_kb_dir", str(kb_dir))

        chat_response = client.post(
            "/api/v1/coach/chat",
            json={
                "user_id": 1,
                "lesson_id": lesson.id,
                "card_id": card.id,
                "message": "帮我总结这张卡的问题",
            },
        )
        assert chat_response.status_code == 200
        events = [json.loads(line) for line in chat_response.text.splitlines() if line.strip()]
        thread_id = next(event["thread_id"] for event in events if event["type"] == "done")

        thread_response = client.get(f"/api/v1/coach/threads/{thread_id}", params={"user_id": 1})
        assert thread_response.status_code == 200
        assert thread_response.json()["data"]["thread_id"] == thread_id

        messages_response = client.get(
            f"/api/v1/coach/threads/{thread_id}/messages",
            params={"user_id": 1},
        )
        assert messages_response.status_code == 200
        messages = messages_response.json()["data"]
        assert len(messages) == 2
        assert messages[1]["content"] == "这是答疑结果。"
