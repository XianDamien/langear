"""Collection-scoped deck preferences; scheduling execution is a separate feature."""
from typing import Annotated
from pydantic import Field
from core.schemas import Body
from core.models import DEFAULT_SCHEDULING


class DeckSettingsUpdate(Body):
    daily_new_limit: int = Field(ge=0, le=10000, strict=True)
    daily_review_limit: int = Field(ge=0, le=10000, strict=True)
    desired_retention: float = Field(gt=0, lt=1, strict=True)
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
    chain, seen = [deck], {deck.id}
    while chain[-1].parent_id and chain[-1].parent_id not in seen:
        parent = service.repo.standard_deck(chain[-1].parent_id)
        seen.add(parent.id)
        chain.append(parent)
    config = {**DEFAULT_SCHEDULING, **service.collection.scheduling_config}
    for row in reversed(chain):
        config.update(row.scheduling_config)
    return {
        "deck_id": str(deck.id), "deck_title": deck.name,
        "scheduling_enabled": False,
        **{wire: config[key] for wire, key in KEYS.items()},
    }


def save_deck_settings(service, deck_id, body):
    service.repo.lock()
    deck = service.repo.standard_deck(deck_id)
    deck.scheduling_config = {
        **deck.scheduling_config,
        **{KEYS[key]: value for key, value in body.model_dump().items()},
    }
    service.db.flush()
    return get_deck_settings(service, deck_id)
