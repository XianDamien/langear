"""Read the shared Library and copy its content into a learner Collection."""

from collections import defaultdict

from sqlalchemy import func, select

from core.content import LIBRARY_SOURCE, ContentService, is_library_copy
from core.courses import deck_sort_key
from core.errors import DomainError, missing
from core.models import Card, CardTemplate, Collection, Deck, Note


def shared_collection(db):
    library = db.scalar(select(Collection).where(Collection.kind == "library"))
    if library is None:
        missing()
    return library


def _conflict(message, details=None):
    raise DomainError(409, "LIBRARY_IMPORT_CONFLICT", message, details or {})


def library_cards(db, deck_id, *, include_descendants=False, limit=100, offset=0):
    library = shared_collection(db)
    deck = db.scalar(select(Deck).where(Deck.collection_id == library.id, Deck.id == deck_id))
    if deck is None or deck.kind != "standard":
        missing()
    service = ContentService(db, library)
    deck_ids = service.repo.descendants(deck.id) if include_descendants else [deck.id]
    condition = (Card.collection_id == library.id, Card.deck_id.in_(deck_ids))
    total = db.scalar(select(func.count(Card.id)).where(*condition))
    cards = db.scalars(
        select(Card).where(*condition).order_by(Card.id).limit(limit).offset(offset)
    )
    return {
        "cards": [service.render(card) for card in cards],
        "total": total,
        "limit": limit,
        "offset": offset,
        "scope": "subtree" if include_descendants else "deck",
    }


def _name_taken(db, collection_id, parent_id, name, exclude_id=None):
    query = select(Deck.id).where(
        Deck.collection_id == collection_id,
        Deck.kind == "standard",
        Deck.name == name,
        Deck.parent_id.is_(None) if parent_id is None else Deck.parent_id == parent_id,
    )
    if exclude_id is not None:
        query = query.where(Deck.id != exclude_id)
    return db.scalar(query) is not None


def import_library_deck(db, collection, deck_id):
    """Idempotently clone a shared deck and its complete descendant subtree.

    Re-imports only add what is missing. Learner-owned deck names, note fields,
    card scheduling and review history are never overwritten, and an existing
    card is never moved to another deck.
    """
    if collection.kind != "user":
        raise DomainError(403, "LIBRARY_READ_ONLY", "System Library is read-only.")
    library = shared_collection(db)
    source_decks = list(
        db.scalars(
            select(Deck).where(Deck.collection_id == library.id, Deck.kind == "standard")
        )
    )
    by_id = {deck.id: deck for deck in source_decks}
    root = by_id.get(deck_id)
    if root is None:
        missing()

    children = defaultdict(list)
    for deck in source_decks:
        children[deck.parent_id].append(deck)
    for siblings in children.values():
        siblings.sort(key=lambda deck: (deck_sort_key(deck.name), deck.name))
    subtree, visited = [], set()

    def collect(current):
        if current.id in visited:
            return
        visited.add(current.id)
        subtree.append(current)
        for child in children.get(current.id, []):
            collect(child)

    collect(root)

    existing_decks = {
        deck.deck_guid: deck
        for deck in db.scalars(select(Deck).where(Deck.collection_id == collection.id))
    }
    cloned_ids = {}
    created_decks = 0
    for source in subtree:
        target = existing_decks.get(source.deck_guid)
        if source.id == root.id:
            # The requested root keeps whatever position the learner chose.
            parent_id = target.parent_id if target is not None else None
        else:
            # Descendants mirror the Library hierarchy so the subtree is whole.
            parent_id = cloned_ids.get(source.parent_id)
        if target is None:
            if _name_taken(db, collection.id, parent_id, source.name):
                _conflict(
                    "A Deck with this name already exists in My Courses.",
                    {"deck_name": source.name},
                )
            target = Deck(
                collection_id=collection.id,
                name=source.name,
                deck_guid=source.deck_guid,
                kind="standard",
                imported=False,
                in_my_courses=True,
                parent_id=parent_id,
                source_metadata={
                    "source": LIBRARY_SOURCE,
                    "library_deck_id": str(source.id),
                    "library_parent_id": str(parent_id) if parent_id else None,
                },
                scheduling_config={},
            )
            db.add(target)
            db.flush()
            existing_decks[source.deck_guid] = target
            created_decks += 1
        else:
            if target.kind != "standard" or not is_library_copy(target):
                _conflict(
                    "A Deck with the same identity did not come from the shared Library.",
                    {"deck_guid": source.deck_guid},
                )
            metadata = dict(target.source_metadata or {})
            previous_parent = metadata.get("library_parent_id", object())
            current_parent = str(target.parent_id) if target.parent_id else None
            if (
                target.parent_id != parent_id
                and previous_parent == current_parent
            ):
                if _name_taken(
                    db, collection.id, parent_id, target.name, exclude_id=target.id
                ):
                    _conflict(
                        "A Deck with this name already exists where the Library copy belongs.",
                        {"deck_name": target.name},
                    )
                target.parent_id = parent_id
                metadata["library_parent_id"] = str(parent_id) if parent_id else None
            elif target.parent_id == parent_id:
                metadata["library_parent_id"] = current_parent
            target.in_my_courses = True
            target.source_metadata = {
                **metadata,
                "source": LIBRARY_SOURCE,
                "library_deck_id": str(source.id),
            }
        cloned_ids[source.id] = target.id

    source_cards = list(
        db.scalars(
            select(Card)
            .where(
                Card.collection_id == library.id,
                Card.deck_id.in_([deck.id for deck in subtree]),
            )
            .order_by(Card.id)
        )
    )
    note_ids = {card.note_id for card in source_cards}
    source_notes = (
        list(
            db.scalars(
                select(Note).where(
                    Note.collection_id == library.id, Note.id.in_(note_ids)
                )
            )
        )
        if note_ids
        else []
    )
    existing_notes = (
        {
            note.guid: note
            for note in db.scalars(
                select(Note).where(
                    Note.collection_id == collection.id,
                    Note.guid.in_([note.guid for note in source_notes]),
                )
            )
        }
        if source_notes
        else {}
    )
    service = ContentService(db, collection)
    note_map, created_notes, warnings = {}, 0, []
    for source in source_notes:
        target = existing_notes.get(source.guid)
        if target is None:
            target = Note(
                collection_id=collection.id,
                guid=source.guid,
                note_type_id=source.note_type_id,
                fields=dict(source.fields),
                tags=list(source.tags or []),
                revision=source.revision,
                imported=False,
                source_metadata={
                    "source": LIBRARY_SOURCE,
                    "library_deck_id": str(root.id),
                    "library_note_id": str(source.id),
                },
            )
            db.add(target)
            db.flush()
            try:
                fields, media = service.validate_fields(
                    target.note_type_id, target.fields
                )
            except DomainError:
                # Shared content wins over local validation: keep the fields so
                # the copy stays complete, and report what could not be linked.
                warnings.append(
                    {
                        "note_guid": source.guid,
                        "code": "NOTE_FIELDS_NOT_VALIDATED",
                    }
                )
            else:
                target.fields = fields
                service.sync_media(target, media)
            existing_notes[source.guid] = target
            created_notes += 1
        elif not is_library_copy(target):
            _conflict(
                "A Note with the same identity did not come from the shared Library.",
                {"note_guid": source.guid},
            )
        note_map[source.id] = target

    existing_cards = (
        {
            (card.note_id, card.card_template_id): card
            for card in db.scalars(
                select(Card).where(
                    Card.collection_id == collection.id,
                    Card.note_id.in_([note.id for note in note_map.values()]),
                )
            )
        }
        if note_map
        else {}
    )
    templates = {template.id: template for template in db.scalars(select(CardTemplate))}
    created_cards = existing_card_count = 0
    skipped_cards = []
    for source in source_cards:
        target_note = note_map[source.note_id]
        target_deck_id = cloned_ids[source.deck_id]
        template = templates[source.card_template_id]
        if target_note.note_type_id != template.note_type_id:
            skipped_cards.append(
                {
                    "card_id": str(source.id),
                    "card_template_key": template.key,
                    "reason": "NOTE_TYPE_CHANGED",
                }
            )
            continue
        current = existing_cards.get((target_note.id, template.id))
        if current is not None:
            existing_card_count += 1
            if current.deck_id != target_deck_id:
                skipped_cards.append(
                    {
                        "card_id": str(current.id),
                        "card_template_key": template.key,
                        "reason": "CARD_ALREADY_IN_ANOTHER_DECK",
                        "deck_id": str(current.deck_id),
                    }
                )
            continue
        # Copy the source card even when the current template would refuse to
        # generate it: a shared card is never silently dropped on import.
        card = Card(
            collection_id=collection.id,
            note_id=target_note.id,
            note_type_id=target_note.note_type_id,
            card_template_id=template.id,
            template_ord=template.ord,
            deck_id=target_deck_id,
            new_position=service.next_position(),
        )
        db.add(card)
        db.flush()
        existing_cards[(target_note.id, template.id)] = card
        created_cards += 1
    return {
        "imported": True,
        "deck_id": str(cloned_ids[root.id]),
        "deck_ids": [str(cloned_ids[deck.id]) for deck in subtree],
        "created": {
            "decks": created_decks,
            "notes": created_notes,
            "cards": created_cards,
        },
        "existing": {
            "decks": len(subtree) - created_decks,
            "notes": len(note_map) - created_notes,
            "cards": existing_card_count,
        },
        "skipped_cards": skipped_cards,
        "warnings": warnings,
    }
