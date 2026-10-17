"""Small deck settings form backed by the effective Review scheduling policy."""
from typing import Annotated
from pydantic import Field
from core.schemas import Body
from core.models import Deck
from core.scheduling import effective
from sqlalchemy import select


class DeckSettingsUpdate(Body):
    daily_new_limit: int = Field(ge=0, le=10000, strict=True)
    daily_review_limit: int = Field(ge=0, le=10000, strict=True)
    desired_retention: float = Field(ge=0.7, le=0.99, strict=True)
    maximum_interval: int = Field(ge=1, le=36500, strict=True)
    learning_steps: list[Annotated[int, Field(gt=0, strict=True)]] = Field(max_length=100)
    relearning_steps: list[Annotated[int, Field(gt=0, strict=True)]] = Field(max_length=100)


KEYS = {
    "daily_new_limit": "new_limit",
    "daily_review_limit": "review_limit",
    "desired_retention": "desired_retention",
    "maximum_interval": "maximum_review_interval",
    "learning_steps": "learning_steps",
    "relearning_steps": "relearning_steps",
}


def get_deck_settings(service, deck_id):
    deck = service.repo.standard_deck(deck_id)
    decks = {row.id: row for row in service.db.scalars(select(Deck).where(Deck.collection_id == service.collection.id))}
    config = effective(service.collection, deck.id, decks)
    return {
        "deck_id": str(deck.id), "deck_title": deck.name,
        "scheduling_enabled": True,
        **{wire: config[key] for wire, key in KEYS.items()},
    }


def save_deck_settings(service, deck_id, body):
    service.repo.lock()
    deck = service.repo.standard_deck(deck_id)
    current = get_deck_settings(service, deck_id)
    for key in ("maximum_interval", "learning_steps", "relearning_steps"):
        if getattr(body, key) != current[key]:
            from core.errors import DomainError
            raise DomainError(422, "COLLECTION_SETTING_ONLY", "This setting is managed by the Collection.")
    deck.scheduling_config = {
        **deck.scheduling_config,
        **{KEYS[key]: value for key, value in body.model_dump().items()
           if key in ("daily_new_limit", "daily_review_limit", "desired_retention")},
    }
    service.db.flush()
    return get_deck_settings(service, deck_id)
