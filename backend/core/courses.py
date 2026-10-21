"""Deck hierarchy, membership and per-deck statistics for Library and My Courses.

Statistics are raw counts from core Card rows. They are intentionally not
quota-limited, so a parent Deck's numbers are the sum of its own subtree and
never change with the order a learner opens subdecks.
"""

import re

from sqlalchemy import select

from core.content import ContentService
from core.models import Card, Deck, Note, utcnow
from core.scheduling import study_day

_NUMERIC_PART = re.compile(r"(\d+)")


def deck_sort_key(name):
    """Natural order so Lesson 2 precedes Lesson 10."""
    return tuple(
        (0, int(part), "") if part.isdigit() else (1, 0, part.casefold())
        for part in _NUMERIC_PART.split(name)
    )


def _sort_decks(decks):
    return sorted(decks, key=lambda deck: (deck_sort_key(deck.name), deck.name))


def card_rows(db, collection):
    return db.execute(
        select(Card, Note.imported)
        .join(Note, Card.note_id == Note.id)
        .where(Card.collection_id == collection.id)
    ).all()


def deck_statistics(db, collection, decks):
    """One pass over Cards; parents aggregate their descendants."""
    by_deck = {deck.id: [] for deck in decks}
    rows = card_rows(db, collection)
    for card, _imported in rows:
        if card.deck_id in by_deck:
            by_deck[card.deck_id].append(card)
    children = {}
    for deck in decks:
        children.setdefault(deck.parent_id, []).append(deck.id)

    def subtree(deck_id):
        result = list(by_deck.get(deck_id, []))
        for child_id in children.get(deck_id, []):
            result.extend(subtree(child_id))
        return result

    today = study_day(utcnow(), collection.timezone)
    stats = {}
    for deck in decks:
        cards = subtree(deck.id)
        selected = (deck.scheduling_config or {}).get("study_card_ids")
        scoped = (
            cards
            if selected is None
            else [card for card in cards if str(card.id) in selected]
        )
        stats[deck.id] = {
            "total_cards": len(cards),
            "note_count": len({card.note_id for card in cards}),
            "selected_cards": len(scoped),
            "new_cards": sum(card.queue == "new" for card in scoped),
            "learning_cards": sum(
                card.queue in ("learning", "day_learning") for card in scoped
            ),
            "review_cards": sum(
                card.queue == "review" and card.due_day is not None and card.due_day <= today
                for card in scoped
            ),
            "completed_cards": sum(card.reps > 0 for card in scoped),
        }
        stats[deck.id]["due_cards"] = (
            stats[deck.id]["new_cards"]
            + stats[deck.id]["learning_cards"]
            + stats[deck.id]["review_cards"]
        )
    return stats


def deck_content_statistics(db, collection, decks):
    """Count Library content without reading scheduling fields."""
    own_cards = {deck.id: 0 for deck in decks}
    own_notes = {deck.id: set() for deck in decks}
    children = {}
    for deck in decks:
        children.setdefault(deck.parent_id, []).append(deck.id)
    for deck_id, note_id in db.execute(
        select(Card.deck_id, Card.note_id).where(Card.collection_id == collection.id)
    ):
        if deck_id in own_cards:
            own_cards[deck_id] += 1
            own_notes[deck_id].add(note_id)

    totals = {}

    def subtree(deck_id):
        if deck_id not in totals:
            count = own_cards[deck_id]
            notes = set(own_notes[deck_id])
            for child_id in children.get(deck_id, []):
                child_count, child_notes = subtree(child_id)
                count += child_count
                notes.update(child_notes)
            totals[deck_id] = count, notes
        return totals[deck_id]

    return {
        deck.id: {"total_cards": subtree(deck.id)[0], "note_count": len(subtree(deck.id)[1])}
        for deck in decks
    }


def _study_day(db, collection):
    return study_day(utcnow(), collection.timezone)


def deck_node(service, deck, stats, children):
    return {
        **service.deck_data(deck),
        "stats": stats[deck.id],
        "children": children,
    }


def deck_ancestry(deck, by_id):
    """Root-first UUID chain for one Deck; a cycle stops instead of looping."""
    chain, seen = [], set()
    current = deck
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current.id)
        current = by_id.get(current.parent_id)
    return list(reversed(chain))


def deck_rows(service, decks, stats, all_decks=None):
    """Flat Deck list carrying what Library and My Courses both need."""
    by_id = {deck.id: deck for deck in (all_decks if all_decks is not None else decks)}
    return [
        {
            **service.deck_data(deck),
            "depth": len(deck_ancestry(deck, by_id)) - 1,
            "path": [str(value) for value in deck_ancestry(deck, by_id)],
            "stats": stats[deck.id],
        }
        for deck in decks
    ]


def _deck_tree(db, collection, statistics):
    """Nested Standard Deck tree plus a flat list; membership is per Deck."""
    service = ContentService(db, collection)
    decks = _sort_decks(
        db.scalars(
            select(Deck)
            .where(Deck.collection_id == collection.id, Deck.kind == "standard")
            .order_by(Deck.name)
        )
    )
    stats = statistics(db, collection, decks)
    children = {}
    for deck in decks:
        children.setdefault(deck.parent_id, []).append(deck.id)
    by_id = {deck.id: deck for deck in decks}

    def build(deck_id):
        deck = by_id[deck_id]
        return deck_node(
            service,
            deck,
            stats,
            [build(child_id) for child_id in children.get(deck_id, [])],
        )

    roots = [build(child_id) for child_id in children.get(None, [])]
    return {"decks": deck_rows(service, decks, stats), "tree": roots}


def deck_tree(db, collection):
    return _deck_tree(db, collection, deck_statistics)


def library_deck_tree(db, collection, user_collection=None):
    """Read-only content view for the shared library, without scheduling counts."""
    result = _deck_tree(db, collection, deck_content_statistics)
    joined_guids = set()
    if user_collection is not None:
        joined_guids = set(
            db.scalars(
                select(Deck.deck_guid).where(
                    Deck.collection_id == user_collection.id,
                    Deck.kind == "standard",
                )
            )
        )

    def content_only(node):
        node["in_my_courses"] = node["deck_guid"] in joined_guids
        node["children"] = [content_only(child) for child in node["children"]]
        return node

    result["tree"] = [content_only(node) for node in result["tree"]]
    for row in result["decks"]:
        row["in_my_courses"] = row["deck_guid"] in joined_guids
    return result


def my_courses(db, collection):
    decks = _sort_decks(
        db.scalars(
            select(Deck)
            .where(
                Deck.collection_id == collection.id,
                Deck.kind == "standard",
                Deck.in_my_courses.is_(True),
            )
            .order_by(Deck.name)
        )
    )
    stats = deck_statistics(db, collection, decks)
    return {
        "decks": [
            {
                "id": deck.id,
                "name": deck.name,
                "parent_id": deck.parent_id,
                "deck_guid": deck.deck_guid,
                "stats": stats[deck.id],
            }
            for deck in decks
        ]
    }
