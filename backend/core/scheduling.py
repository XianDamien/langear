"""Card scheduling policy around the locked py-fsrs engine; no FSRS formulas."""

from datetime import UTC, date, datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from fsrs import Card as FSRSCard
from fsrs import Rating, Scheduler, State
from pydantic import BaseModel, ConfigDict

from core.models import DEFAULT_SCHEDULING

RATINGS = {r.name.lower(): r for r in Rating}
ORDERS = {
    "new_card_gather_order": (
        "deck",
        "deck_then_random_notes",
        "lowest_position",
        "highest_position",
        "random_notes",
        "random_cards",
    ),
    "new_card_sort_order": (
        "template",
        "order_gathered",
        "template_then_random",
        "random_note_then_template",
        "random_card",
    ),
    "new_review_order": ("mix_with_reviews", "before_reviews", "after_reviews"),
    "interday_learning_review_order": (
        "mix_with_reviews",
        "before_reviews",
        "after_reviews",
    ),
    "review_sort_order": (
        "due_day",
        "due_day_then_deck",
        "deck_then_due_day",
        "interval_ascending",
        "interval_descending",
        "retrievability_ascending",
        "retrievability_descending",
        "relative_overdueness",
        "random",
        "added",
        "reverse_added",
    ),
}
OVERRIDES = set(ORDERS) | {
    "new_limit",
    "review_limit",
    "desired_retention",
    "sibling_burying",
}
SCHEDULE_FIELDS = (
    "type",
    "queue",
    "new_position",
    "due_at",
    "due_day",
    "fsrs_state",
    "reps",
    "lapses",
    "learning_steps_remaining",
    "interval_days",
    "last_reviewed_at",
    "buried_on_day",
)


class MemoryState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    stability: float
    difficulty: float
    step: int | None
    desired_retention: float
    fsrs_algorithm_version: str = "py-fsrs/6.3.0"
    fsrs_config_version: str


def study_day(now, tz):
    local = now.astimezone(ZoneInfo(tz))
    return (local.date() - timedelta(days=local.hour < 4) - date(1970, 1, 1)).days


def day_start(day, tz):
    return datetime.combine(
        date(1970, 1, 1) + timedelta(days=day), time(4), ZoneInfo(tz)
    ).astimezone(UTC)


def restored_queue(card):
    if card.type == "new":
        return "new"
    if card.type == "review":
        return "review"
    return "learning" if card.due_at is not None else "day_learning"


def ancestry(deck_id, decks):
    result = []
    while deck_id is not None:
        result.append(deck_id)
        deck_id = decks[deck_id].parent_id
    return result


def effective(collection, deck_id, decks):
    config = {**DEFAULT_SCHEDULING, **collection.scheduling_config}
    for key in OVERRIDES:
        for ancestor in ancestry(deck_id, decks):
            value = decks[ancestor].scheduling_config.get(key)
            if value is not None:
                config[key] = value
                break
    # Limits are enforced along the full ancestor path, separately from inheritance.
    return config


def engine(config):
    return Scheduler(
        desired_retention=config["desired_retention"],
        learning_steps=[timedelta(minutes=n) for n in config["learning_steps"]],
        relearning_steps=[timedelta(minutes=n) for n in config["relearning_steps"]],
        maximum_interval=config["maximum_review_interval"],
    )


def native(card, now, tz):
    memory = MemoryState.model_validate(card.fsrs_state) if card.fsrs_state else None
    state = {
        "new": State.Learning,
        "learning": State.Learning,
        "review": State.Review,
        "relearning": State.Relearning,
    }[card.type]
    return FSRSCard(
        card_id=card.id.int,
        state=state,
        step=memory.step if memory else 0,
        stability=memory.stability if memory else None,
        difficulty=memory.difficulty if memory else None,
        due=card.due_at or (day_start(card.due_day, tz) if card.due_day else now),
        last_review=card.last_reviewed_at,
    )


def schedule(card, rating, now, collection, config):
    updated, _ = engine(config).review_card(
        native(card, now, collection.timezone), RATINGS[rating], review_datetime=now
    )
    kind = updated.state.name.lower()
    day = study_day(updated.due, collection.timezone)
    is_review = kind == "review"
    interday = day > study_day(now, collection.timezone)
    config_version = sha256(repr(sorted(config.items())).encode()).hexdigest()[:16]
    memory = MemoryState(
        stability=updated.stability,
        difficulty=updated.difficulty,
        step=updated.step,
        desired_retention=config["desired_retention"],
        fsrs_config_version=config_version,
    )
    return {
        "type": kind,
        "queue": "review" if is_review else "day_learning" if interday else "learning",
        "new_position": None,
        "due_at": None if is_review or interday else updated.due,
        "due_day": day if is_review or interday else None,
        "fsrs_state": memory.model_dump(),
        "reps": card.reps + 1,
        "lapses": card.lapses + int(card.type == "review" and rating == "again"),
        "learning_steps_remaining": 0
        if updated.step is None
        else max(
            0,
            len(
                config["relearning_steps" if kind == "relearning" else "learning_steps"]
            )
            - updated.step,
        ),
        "interval_days": (updated.due - now).total_seconds() / 86400,
        "last_reviewed_at": now,
        "buried_on_day": None,
    }


def options(card, now, collection, config):
    result = []
    for rating in RATINGS:
        state = schedule(card, rating, now, collection, config)
        seconds = max(0, round(state["interval_days"] * 86400))
        display = (
            f"{max(1, round(seconds / 86400))}d"
            if seconds >= 86400
            else f"{round(seconds / 3600)}h"
            if seconds >= 3600
            else f"{max(1, round(seconds / 60))}m"
        )
        result.append(
            {
                "rating": rating,
                "display_interval": display,
                "next_type": state["type"],
                "next_queue": state["queue"],
                "due_at": state["due_at"],
                "due_day": state["due_day"],
            }
        )
    return result


def ordered(cards, collection, config, now, decks):
    """Stable per-Study-Day random keys, with Card ID as the final tie-breaker."""
    day = study_day(now, collection.timezone)

    def rand(value):
        return sha256(f"{collection.id}:{day}:{value}".encode()).hexdigest()

    def deck_path(card):
        return tuple(reversed(ancestry(card.original_deck_id or card.deck_id, decks)))

    news = [c for c in cards if c.queue == "new"]
    gather = config["new_card_gather_order"]
    gather_keys = {
        "deck": lambda c: (deck_path(c), c.new_position),
        "deck_then_random_notes": lambda c: (
            deck_path(c),
            rand(c.note_id),
            c.template_ord,
        ),
        "lowest_position": lambda c: (c.new_position,),
        "highest_position": lambda c: (-c.new_position,),
        "random_notes": lambda c: (rand(c.note_id), c.template_ord),
        "random_cards": lambda c: (rand(c.id),),
    }
    news.sort(key=lambda c: (*gather_keys[gather](c), c.id))
    sort = config["new_card_sort_order"]
    if sort == "template":
        news.sort(key=lambda c: c.template_ord)  # stable, preserves gathered order
    elif sort != "order_gathered":
        keys = {
            "template_then_random": lambda c: (c.template_ord, rand(c.id)),
            "random_note_then_template": lambda c: (rand(c.note_id), c.template_ord),
            "random_card": lambda c: (rand(c.id),),
        }
        news.sort(key=lambda c: (*keys[sort](c), c.id))
    reviews = [c for c in cards if c.queue == "review" and c.due_day <= day]

    def retrievability(c):
        return engine(config).get_card_retrievability(
            native(c, now, collection.timezone), current_datetime=now
        )

    keys = {
        "due_day": lambda c: (c.due_day,),
        "due_day_then_deck": lambda c: (c.due_day, deck_path(c)),
        "deck_then_due_day": lambda c: (deck_path(c), c.due_day),
        "interval_ascending": lambda c: (c.interval_days,),
        "interval_descending": lambda c: (-c.interval_days,),
        "retrievability_ascending": lambda c: (retrievability(c),),
        "retrievability_descending": lambda c: (-retrievability(c),),
        "relative_overdueness": lambda c: (
            -(day - c.due_day) / max(c.interval_days, 1),
        ),
        "random": lambda c: (rand(c.id),),
        "added": lambda c: (c.created_at,),
        "reverse_added": lambda c: (-c.created_at.timestamp(),),
    }
    reviews.sort(key=lambda c: (*keys[config["review_sort_order"]](c), c.id))
    learning = sorted(
        [c for c in cards if c.queue == "learning" and c.due_at <= now],
        key=lambda c: (c.due_at, c.id),
    )
    interday = sorted(
        [c for c in cards if c.queue == "day_learning" and c.due_day <= day],
        key=lambda c: (c.due_day, c.id),
    )

    def merge(other, main, mode):
        if mode == "before_reviews":
            return other + main
        if mode == "after_reviews":
            return main + other
        # Evenly spread the smaller queue, preserving each group's relative order.
        result, index = [], 0
        for i, card in enumerate(main):
            target = (i + 1) * len(other) // max(1, len(main))
            result.extend(other[index:target])
            index = target
            result.append(card)
        return result + other[index:]

    return learning + merge(
        news,
        merge(interday, reviews, config["interday_learning_review_order"]),
        config["new_review_order"],
    )
