"""Markdown knowledge-base retrieval for coach answers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

import yaml

from app.config import settings


WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


@dataclass(frozen=True)
class KnowledgeChunk:
    """A retrievable knowledge chunk derived from a markdown document."""

    doc_path: str
    chunk_id: str
    title: str
    tags: list[str]
    text: str
    score: float = 0.0


class CoachKnowledgeBaseService:
    """Searches a local markdown knowledge base."""

    def __init__(self, kb_root: str | None = None):
        self.kb_root = Path(kb_root or settings.coach_kb_dir)

    @staticmethod
    def _tokenize(value: str) -> list[str]:
        return [token.lower() for token in WORD_RE.findall(value)]

    @staticmethod
    def _parse_frontmatter(raw_text: str) -> tuple[dict[str, Any], str]:
        if not raw_text.startswith("---\n"):
            return {}, raw_text

        marker = "\n---\n"
        end_index = raw_text.find(marker, 4)
        if end_index == -1:
            return {}, raw_text

        frontmatter_text = raw_text[4:end_index]
        body = raw_text[end_index + len(marker):]
        try:
            metadata = yaml.safe_load(frontmatter_text) or {}
        except yaml.YAMLError:
            metadata = {}
        return metadata if isinstance(metadata, dict) else {}, body

    @staticmethod
    def _chunk_markdown(body: str, title: str) -> list[str]:
        chunks: list[str] = []
        current_heading = title
        current_lines: list[str] = []

        def flush() -> None:
            if not current_lines:
                return
            text = "\n".join(current_lines).strip()
            if text:
                chunks.append(f"{current_heading}\n{text}".strip())
            current_lines.clear()

        for raw_line in body.splitlines():
            line = raw_line.strip()
            if not line:
                if sum(len(item) for item in current_lines) > 300:
                    flush()
                continue

            if line.startswith("#"):
                flush()
                current_heading = line.lstrip("#").strip() or current_heading
                continue

            current_lines.append(line)
            if sum(len(item) for item in current_lines) > 900:
                flush()

        flush()
        return chunks

    def _iter_chunks(self) -> list[KnowledgeChunk]:
        if not self.kb_root.exists() or not self.kb_root.is_dir():
            return []

        results: list[KnowledgeChunk] = []
        for path in sorted(self.kb_root.rglob("*.md")):
            raw_text = path.read_text(encoding="utf-8")
            metadata, body = self._parse_frontmatter(raw_text)
            title = str(metadata.get("title") or path.stem)
            tags = [
                str(tag).strip()
                for tag in metadata.get("tags", [])
                if str(tag).strip()
            ]
            aliases = [
                str(alias).strip()
                for alias in metadata.get("aliases", [])
                if str(alias).strip()
            ]
            all_tags = [*tags, *aliases]
            for index, chunk_text in enumerate(self._chunk_markdown(body, title), start=1):
                results.append(
                    KnowledgeChunk(
                        doc_path=str(path.relative_to(self.kb_root)),
                        chunk_id=f"{path.stem}:{index}",
                        title=title,
                        tags=all_tags,
                        text=chunk_text,
                    )
                )
        return results

    def build_query(
        self,
        *,
        user_message: str,
        current_card_context: dict[str, Any],
        lesson_feedback_history: list[dict[str, Any]],
    ) -> str:
        """Build a retrieval query from the strongest current learning context."""
        parts = [user_message.strip()]

        card = current_card_context.get("card") or {}
        if card.get("front_text"):
            parts.append(f"原文: {card['front_text']}")
        if card.get("back_text"):
            parts.append(f"翻译: {card['back_text']}")

        latest_feedback = current_card_context.get("latest_feedback") or {}
        if latest_feedback.get("user_transcription_text"):
            parts.append(f"用户转写: {latest_feedback['user_transcription_text']}")

        feedback = latest_feedback.get("feedback") or {}
        for issue in feedback.get("issues", [])[:3]:
            problem = issue.get("problem")
            if problem:
                parts.append(f"问题: {problem}")

        for item in lesson_feedback_history[:2]:
            review_feedback = item.get("feedback") or {}
            for issue in review_feedback.get("issues", [])[:2]:
                problem = issue.get("problem")
                if problem:
                    parts.append(f"lesson历史问题: {problem}")

        return "\n".join(part for part in parts if part).strip()

    def search(
        self,
        *,
        query: str,
        tags: list[str] | None = None,
        top_k: int | None = None,
    ) -> list[dict[str, Any]]:
        """Search markdown chunks by token overlap and tag/title boosts."""
        normalized_tags = {tag.lower() for tag in tags or [] if tag}
        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scored: list[KnowledgeChunk] = []
        for chunk in self._iter_chunks():
            chunk_tokens = self._tokenize(chunk.text)
            title_tokens = self._tokenize(chunk.title)
            tag_tokens = self._tokenize(" ".join(chunk.tags))

            overlap = len(set(query_tokens) & set(chunk_tokens))
            title_overlap = len(set(query_tokens) & set(title_tokens))
            tag_overlap = len(set(query_tokens) & set(tag_tokens))
            selected_tag_bonus = len(normalized_tags & {tag.lower() for tag in chunk.tags})
            score = overlap + title_overlap * 2 + tag_overlap * 2 + selected_tag_bonus * 3
            if score <= 0:
                continue

            scored.append(
                KnowledgeChunk(
                    doc_path=chunk.doc_path,
                    chunk_id=chunk.chunk_id,
                    title=chunk.title,
                    tags=chunk.tags,
                    text=chunk.text,
                    score=float(score),
                )
            )

        scored.sort(key=lambda item: item.score, reverse=True)
        return [
            {
                "source_type": "knowledge_base",
                "doc_path": item.doc_path,
                "chunk_id": item.chunk_id,
                "title": item.title,
                "score": item.score,
                "excerpt": item.text[:500],
                "tags": item.tags,
            }
            for item in scored[: (top_k or settings.coach_kb_top_k)]
        ]

