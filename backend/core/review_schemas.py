from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, field_validator

from core.scheduling import ORDERS, OVERRIDES
from core.schemas import Body


class Scope(Body):
    deck_id: UUID
    include_descendants: bool = True
    exclude_imported: bool = False
    card_template_keys: list[Literal[
        "sentence_retelling", "sentence_translation", "sentence_dictation",
        "vocabulary_english_to_chinese", "vocabulary_chinese_to_english",
    ]] | None = Field(default=None, min_length=1)
    limit: int | None = Field(default=None, ge=1, le=500)


class QueueCreate(Body):
    scope: Scope


class NoInput(Body):
    type: Literal["none"]


class TextInput(Body):
    type: Literal["text"]
    text: str = Field(min_length=1, max_length=100000)

    @field_validator("text")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("Text cannot be blank")
        return value


class AudioInput(Body):
    type: Literal["audio"]
    temporary_media_asset_id: UUID
    realtime_session_id: str | None = Field(default=None, min_length=1, max_length=100)


class Flip(Body):
    card_id: UUID
    review_token: UUID
    input: Annotated[NoInput | TextInput | AudioInput, Field(discriminator="type")]


class Rate(Body):
    rating: Literal["again", "hard", "good", "easy"]
    card_schedule_revision: int = Field(ge=0)


class ScheduleAction(Body):
    action: Literal["suspend", "unsuspend", "bury", "unbury"]
    card_schedule_revision: int = Field(ge=0)


class SchedulingPatch(Body):
    overrides: dict

    @field_validator("overrides")
    @classmethod
    def validate_overrides(cls, values):
        if set(values) - OVERRIDES:
            raise ValueError("Unknown or Collection-only setting")
        for key, value in values.items():
            if value is None:
                continue
            if key in ORDERS:
                if value not in ORDERS[key]:
                    raise ValueError("Unknown display order")
            elif key in ("new_limit", "review_limit"):
                if type(value) is not int or not 0 <= value <= 100000:
                    raise ValueError("Invalid daily limit")
            elif key == "desired_retention":
                if type(value) not in (float, int) or not 0.7 <= value <= 0.99:
                    raise ValueError("Invalid desired retention")
            elif key == "sibling_burying" and type(value) is not bool:
                raise ValueError("Expected boolean")
        return values
