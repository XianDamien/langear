"""Unit tests for the markdown knowledge-base retrieval service."""

from app.services.coach_kb_service import CoachKnowledgeBaseService


def test_search_returns_markdown_hits_with_frontmatter(tmp_path):
    kb_dir = tmp_path / "kb"
    kb_dir.mkdir()
    (kb_dir / "pronunciation.md").write_text(
        """---
title: 发音纠错
tags:
  - pronunciation
  - stress
aliases:
  - 读音
---

# 发音问题

当学生出现发音错误时，先指出问题音，再给出可重复跟读的短练习。
""",
        encoding="utf-8",
    )

    service = CoachKnowledgeBaseService(str(kb_dir))
    hits = service.search(query="我这句发音不准应该怎么练", tags=["pronunciation"], top_k=3)

    assert len(hits) == 1
    assert hits[0]["doc_path"] == "pronunciation.md"
    assert hits[0]["title"] == "发音纠错"
    assert "发音错误" in hits[0]["excerpt"]


def test_build_query_prefers_card_context_and_feedback():
    service = CoachKnowledgeBaseService("/tmp/non-existent-kb")
    query = service.build_query(
        user_message="为什么我这里说得不自然",
        current_card_context={
            "card": {
                "front_text": "Could I have a glass of water?",
                "back_text": "我可以要一杯水吗？",
            },
            "latest_feedback": {
                "user_transcription_text": "Could I have water",
                "feedback": {
                    "issues": [
                        {"problem": "礼貌表达缺失"},
                    ]
                },
            },
        },
        lesson_feedback_history=[],
    )

    assert "Could I have a glass of water?" in query
    assert "我可以要一杯水吗？" in query
    assert "Could I have water" in query
    assert "礼貌表达缺失" in query
