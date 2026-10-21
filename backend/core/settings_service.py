"""Collection-wide study settings, independent of any single Deck.

A Study Session default can be either inherited scheduling values or an
explicit list of core Deck UUIDs (`default_deck_scope`). Deck-level overrides
stay on `PUT /api/v1/decks/{deck_id}/settings`.
"""

from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator
from sqlalchemy import select

from core.models import DEFAULT_SCHEDULING, Deck
from core.schemas import Body

STEP_KEYS = ("learning_steps", "relearning_steps")
SCOPE_KEY = "default_deck_scope"


class SettingsUpdate(Body):
    new_limit: int | None = Field(default=None, ge=0, le=10000, strict=True)
    desired_retention: float | None = Field(default=None, ge=0.7, le=0.99, strict=True)
    learning_steps: list[Annotated[int, Field(gt=0, strict=True)]] | None = Field(
        default=None, max_length=100
    )
    relearning_steps: list[Annotated[int, Field(gt=0, strict=True)]] | None = Field(
        default=None, max_length=100
    )
    maximum_review_interval: int | None = Field(
        default=None, ge=1, le=36500, strict=True
    )
    default_deck_scope: list[UUID] | None = Field(default=None, max_length=500)

    @field_validator("default_deck_scope")
    @classmethod
    def unique_scope(cls, values):
        if values is None:
            return None
        if len(set(values)) != len(values):
            raise ValueError("Deck scope cannot contain duplicates")
        return values


def settings_data(collection):
    config = {**DEFAULT_SCHEDULING, **(collection.scheduling_config or {})}
    return {
        "new_limit": config["new_limit"],
        "desired_retention": config["desired_retention"],
        "learning_steps": config["learning_steps"],
        "relearning_steps": config["relearning_steps"],
        "maximum_review_interval": config["maximum_review_interval"],
        "default_deck_scope": [str(value) for value in collection.default_deck_scope or []],
    }


def save_settings(service, body):
    """`None` means "leave unchanged"; explicit values are validated on the wire."""
    collection = service.repo.lock()
    updates = body.model_dump(exclude_unset=True)
    if body.default_deck_scope is not None:
        requested = set(body.default_deck_scope)
        owned = set(
            service.db.scalars(
                select(Deck.id).where(
                    Deck.collection_id == collection.id,
                    Deck.kind == "standard",
                    Deck.id.in_(requested),
                )
            )
        )
        if owned != requested:
            from core.errors import DomainError

            raise DomainError(
                422,
                "DECK_SCOPE_INVALID",
                "The default scope may only contain this Collection's Standard Decks.",
            )
        collection.default_deck_scope = [
            str(value) for value in body.default_deck_scope
        ]
    config = dict(collection.scheduling_config or {})
    mapping = {
        "new_limit": "new_limit",
        "desired_retention": "desired_retention",
        "learning_steps": "learning_steps",
        "relearning_steps": "relearning_steps",
        "maximum_review_interval": "maximum_review_interval",
    }
    for wire, key in mapping.items():
        if wire in updates and updates[wire] is not None:
            config[key] = getattr(body, wire)
    collection.scheduling_config = config
    service.db.flush()
    return settings_data(collection)
