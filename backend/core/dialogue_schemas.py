from uuid import UUID
from pydantic import Field
from core.schemas import Body


class DialogueCreate(Body):
    deck_id: UUID
    review_queue_id: UUID
    entry_key: UUID
    attempt_ids: list[UUID] = Field(min_length=1, max_length=1000)


class Source(Body):
    attempt_id: UUID
    card_id: UUID


class Goal(Body):
    id: str = Field(min_length=1, max_length=100)
    description_zh: str = Field(min_length=1, max_length=2000)


class TargetExpression(Body):
    english: str = Field(min_length=1, max_length=2000)
    meaning_zh: str = Field(default='', max_length=2000)
    source: Source


class Scenario(Body):
    title: str = Field(min_length=1, max_length=2000)
    setup_zh: str = Field(min_length=1, max_length=2000)
    learner_role: str = Field(min_length=1, max_length=2000)
    agent_role: str = Field(min_length=1, max_length=2000)
    goals: list[Goal] = Field(min_length=1, max_length=3)
    target_expressions: list[TargetExpression] = Field(max_length=3)
