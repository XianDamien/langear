"""Content operations serialize per Collection; history is never re-rendered."""

from uuid import UUID
from sqlalchemy import delete, exists, or_, select, update
from core import confirmation
from core.errors import DomainError, missing
from core.models import (
    Attempt,
    Card,
    CardTemplate,
    Collection,
    Deck,
    MediaAsset,
    MediaReference,
    Note,
    NoteType,
    NoteTypeField,
)
from core.repository import ContentRepository


LIBRARY_SOURCE = "library"


def is_library_copy(row):
    return (row.source_metadata or {}).get("source") == LIBRARY_SOURCE


def present(value):
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def tags(values):
    if any(not value.strip() or len(value) > 100 for value in values):
        raise DomainError(
            422, "VALIDATION_ERROR", "Tags must contain 1–100 characters."
        )
    return list(dict.fromkeys(value.strip() for value in values))


class ContentService:
    def __init__(self, db, collection):
        self.db, self.collection = db, collection
        self.repo = ContentRepository(db, collection)
        self.media_cleanup_candidates = set()

    def note_type(self, key):
        nt = self.db.scalar(select(NoteType).where(NoteType.key == key))
        if nt is None:
            raise DomainError(422, "NOTETYPE_INVALID", "Unknown system NoteType.")
        return nt

    def fields_for(self, nt_id):
        return list(
            self.db.scalars(
                select(NoteTypeField)
                .where(NoteTypeField.note_type_id == nt_id)
                .order_by(NoteTypeField.ord)
            )
        )

    def templates_for(self, nt_id):
        return list(
            self.db.scalars(
                select(CardTemplate)
                .where(CardTemplate.note_type_id == nt_id)
                .order_by(CardTemplate.ord)
            )
        )

    def validate_fields(self, nt_id, values, mapping=False):
        definitions = {field.key: field for field in self.fields_for(nt_id)}
        code = "NOTETYPE_FIELD_MAPPING_INVALID" if mapping else "NOTE_FIELDS_INVALID"
        unknown = sorted(set(values) - definitions.keys())
        missing_fields = [
            key
            for key, field in definitions.items()
            if field.required and not present(values.get(key))
        ]
        if unknown or missing_fields:
            raise DomainError(
                422,
                code,
                "Note fields do not match the NoteType.",
                {"unknown_fields": unknown, "missing_fields": missing_fields},
            )
        cleaned, media = {}, []
        for key, value in values.items():
            if not present(value):
                continue
            if len(value) > 100000:
                raise DomainError(422, code, "Note field is too long.", {"field": key})
            field = definitions[key]
            if field.kind == "text":
                cleaned[key] = value
                continue
            try:
                asset_id = UUID(value)
            except (ValueError, TypeError):
                raise DomainError(
                    422, code, "Media fields require a MediaAsset UUID.", {"field": key}
                )
            asset = self.db.scalar(
                select(MediaAsset).where(
                    MediaAsset.id == asset_id,
                    or_(
                        MediaAsset.collection_id == self.collection.id,
                        MediaAsset.scope == "library_shared",
                    ),
                )
            )
            if asset is None:
                missing()
            if asset.kind != field.kind or asset.lifecycle != "ready":
                raise DomainError(
                    422,
                    code,
                    "Media kind or lifecycle does not match the field.",
                    {"field": key},
                )
            cleaned[key] = str(asset.id)
            media.append((key, asset))
        return cleaned, media

    def sync_media(self, note, references):
        self.media_cleanup_candidates.update(
            self.db.scalars(
                select(MediaReference.media_asset_id).where(
                    MediaReference.collection_id == self.collection.id,
                    MediaReference.note_id == note.id,
                )
            )
        )
        self.db.execute(
            delete(MediaReference).where(
                MediaReference.collection_id == self.collection.id,
                MediaReference.note_id == note.id,
            )
        )
        for key, asset in references:
            self.db.add(
                MediaReference(
                    collection_id=self.collection.id,
                    note_id=note.id,
                    field_key=key,
                    media_asset_id=asset.id,
                    media_collection_id=asset.collection_id,
                    media_scope=asset.scope,
                )
            )
        self.db.flush()

    def cleanup_media(self):
        # Lifecycle marking only; LAN-33's asynchronous collector owns OSS deletion.
        self.db.execute(
            update(MediaAsset)
            .where(
                MediaAsset.id.in_(self.media_cleanup_candidates),
                MediaAsset.collection_id == self.collection.id,
                MediaAsset.scope == "private",
                MediaAsset.lifecycle == "ready",
                ~exists(
                    select(MediaReference.id).where(
                        MediaReference.media_asset_id == MediaAsset.id
                    )
                ),
                ~exists(
                    select(Attempt.id).where(Attempt.media_asset_id == MediaAsset.id)
                ),
            )
            .values(lifecycle="pending_delete")
        )

    def deck_data(self, deck):
        return {
            "id": deck.id,
            "name": deck.name,
            "parent_id": deck.parent_id,
            "kind": deck.kind,
            "deck_guid": deck.deck_guid,
            "in_my_courses": deck.in_my_courses,
            "scheduling_config": deck.scheduling_config,
            "source_metadata": deck.source_metadata or {},
        }

    def create_deck(self, body):
        self.repo.lock()
        if body.parent_id:
            self.repo.standard_deck(body.parent_id)
        deck = Deck(
            collection_id=self.collection.id, name=body.name, parent_id=body.parent_id
        )
        self.db.add(deck)
        self.db.flush()
        return self.deck_data(deck)

    def update_deck(self, deck_id, body):
        self.repo.lock()
        deck = self.repo.standard_deck(deck_id)
        if body.parent_id:
            self.repo.standard_deck(body.parent_id)
            if body.parent_id in self.repo.descendants(deck_id):
                raise DomainError(
                    422, "DECK_HIERARCHY_CYCLE", "A Deck cannot be its own ancestor."
                )
        deck.name, deck.parent_id = body.name, body.parent_id
        self.db.flush()
        return self.deck_data(deck)

    def render(self, card, *, note=None, template=None):
        note = self.repo.get(Note, card.note_id) if note is None else note
        template = self.db.get(CardTemplate, card.card_template_id) if template is None else template
        fields = note.fields
        missing_fields = [
            key for key in template.required_fields if not present(fields.get(key))
        ]
        return {
            "id": card.id,
            "note_id": note.id,
            "note_guid": note.guid,
            "deck_id": card.deck_id,
            "card_template_key": template.key,
            "template_ord": card.template_ord,
            "note_revision": note.revision,
            "card_schedule_revision": card.schedule_revision,
            "front": {
                key: fields[key]
                for key in template.q_format
                if present(fields.get(key))
            },
            "back": {
                key: fields[key]
                for key in template.a_format
                if present(fields.get(key))
            },
            "answer": {template.answer_field: fields.get(template.answer_field)},
            "input_requirement": {
                "type": template.input_type,
                "required": template.input_type != "none",
            },
            "renderable": not missing_fields,
            "missing_fields": missing_fields,
            "type": card.type,
            "queue": card.queue,
            "new_position": card.new_position,
            "due_at": card.due_at,
            "due_day": card.due_day,
            "fsrs_state": card.fsrs_state,
            "reps": card.reps,
            "lapses": card.lapses,
        }

    def note_data(self, note):
        cards = self.db.scalars(
            select(Card)
            .where(Card.collection_id == self.collection.id, Card.note_id == note.id)
            .order_by(Card.template_ord)
        ).all()
        return {
            "id": note.id,
            "guid": note.guid,
            "note_type_key": self.db.get(NoteType, note.note_type_id).key,
            "fields": note.fields,
            "tags": note.tags,
            "revision": note.revision,
            "cards": [self.render(card) for card in cards],
        }

    def next_position(self):
        """UPDATE ... RETURNING is atomic even across processes. Never MAX+1."""
        return self.db.scalar(
            update(Collection)
            .where(Collection.id == self.collection.id)
            .values(next_new_position=Collection.next_new_position + 1)
            .returning(Collection.next_new_position)
        )

    def generate(self, note, deck_id, card_template_key=None):
        deck = self.repo.standard_deck(deck_id)
        existing = set(
            self.db.scalars(
                select(Card.card_template_id).where(
                    Card.collection_id == self.collection.id, Card.note_id == note.id
                )
            )
        )
        created, skipped = [], []
        for template in self.templates_for(note.note_type_id):
            if card_template_key is not None and template.key != card_template_key:
                continue
            missing_fields = [
                key
                for key in template.required_fields
                if not present(note.fields.get(key))
            ]
            if missing_fields:
                skipped.append(
                    {
                        "card_template_key": template.key,
                        "missing_fields": missing_fields,
                    }
                )
            elif template.id not in existing:
                position = self.next_position()
                card = Card(
                    collection_id=self.collection.id,
                    note_id=note.id,
                    note_type_id=note.note_type_id,
                    card_template_id=template.id,
                    template_ord=template.ord,
                    deck_id=deck.id,
                    new_position=position,
                )
                self.db.add(card)
                self.db.flush()
                created.append(card.id)
        return {"cards_created": created, "skipped_templates": skipped}

    def create_note(self, body):
        self.repo.lock()
        nt = self.note_type(body.note_type_key)
        fields, media = self.validate_fields(nt.id, body.fields)
        self.repo.standard_deck(body.deck_id)
        if body.card_template_key is not None:
            template = next(
                (
                    t
                    for t in self.templates_for(nt.id)
                    if t.key == body.card_template_key
                ),
                None,
            )
            if template is None:
                raise DomainError(
                    422, "CARD_TEMPLATE_INVALID", "Choose a template for this NoteType."
                )
            missing_fields = [
                key for key in template.required_fields if not present(fields.get(key))
            ]
            if missing_fields:
                raise DomainError(
                    422,
                    "NOTE_FIELDS_INVALID",
                    "Required fields are missing for this card type.",
                    {"missing_fields": missing_fields},
                )
        note = Note(
            collection_id=self.collection.id,
            note_type_id=nt.id,
            fields=fields,
            tags=tags(body.tags),
        )
        if body.guid is not None:
            note.guid = body.guid
        self.db.add(note)
        self.db.flush()
        self.sync_media(note, media)
        generation = self.generate(note, body.deck_id, body.card_template_key)
        return {**self.note_data(note), **generation}

    def edit_note(self, note_id, body):
        self.repo.lock()
        note = self.repo.get(Note, note_id)
        if note.revision != body.revision:
            raise DomainError(
                409,
                "NOTE_REVISION_CONFLICT",
                "The note was updated by another request.",
                {"current_revision": note.revision},
            )
        fields, media = self.validate_fields(note.note_type_id, body.fields)
        note.fields, note.revision = fields, note.revision + 1
        if body.tags is not None:
            note.tags = tags(body.tags)
        self.sync_media(note, media)
        self.cleanup_media()
        self.db.flush()
        return self.note_data(note)

    def generate_missing(self, note_id, body):
        self.repo.lock()
        note = self.repo.get(Note, note_id)
        generation = self.generate(note, body.deck_id)
        return {**self.note_data(note), **generation}

    def move_card(self, card_id, deck_id):
        self.repo.lock()
        card = self.repo.get(Card, card_id)
        if card.original_deck_id is not None:
            raise DomainError(
                422,
                "FILTERED_CARD_MOVE_FORBIDDEN",
                "Return the Card from its Filtered Deck first.",
            )
        card.deck_id = self.repo.standard_deck(deck_id).id
        self.db.flush()
        return self.render(card)

    def affected(self, resource_type, resource_id):
        model = {"note": Note, "card": Card, "deck": Deck}[resource_type]
        resource = self.repo.get(model, resource_id)
        deck_ids, note_ids = [], []
        if resource_type == "note":
            note_ids = [resource.id]
            condition = Card.note_id == resource.id
        elif resource_type == "card":
            condition = Card.id == resource.id
        else:
            deck_ids = self.repo.descendants(resource.id)
            condition = or_(
                Card.deck_id.in_(deck_ids), Card.original_deck_id.in_(deck_ids)
            )
            # A Filtered Deck deletion returns cards instead of deleting them.
            if resource.kind == "filtered":
                condition = Card.id.is_(None)
        cards = self.db.scalars(
            select(Card)
            .where(Card.collection_id == self.collection.id, condition)
            .order_by(Card.id)
            .with_for_update()
        ).all()
        card_ids = [card.id for card in cards]
        if resource_type == "deck" and resource.kind == "standard" and cards:
            # Only Library-sourced notes made unreachable by this deletion are
            # removed; user-authored notes keep the historical behaviour.
            candidate_note_ids = {card.note_id for card in cards}
            surviving_note_ids = set(
                self.db.scalars(
                    select(Card.note_id).where(
                        Card.collection_id == self.collection.id,
                        Card.note_id.in_(candidate_note_ids),
                        Card.id.not_in(card_ids),
                    )
                )
            )
            note_ids = list(
                self.db.scalars(
                    select(Note.id).where(
                        Note.collection_id == self.collection.id,
                        Note.id.in_(candidate_note_ids - surviving_note_ids),
                        Note.source_metadata["source"].astext == LIBRARY_SOURCE,
                    )
                )
            )
        attempts = self.db.scalars(
            select(Attempt)
            .where(
                Attempt.collection_id == self.collection.id,
                Attempt.card_id.in_(card_ids),
            )
            .order_by(Attempt.id)
            .with_for_update()
        ).all()
        refs = self.db.scalars(
            select(MediaReference)
            .where(
                MediaReference.collection_id == self.collection.id,
                MediaReference.note_id.in_(note_ids),
            )
            .order_by(MediaReference.id)
        ).all()
        borrowed = (
            self.db.scalars(
                select(Card)
                .where(
                    Card.collection_id == self.collection.id,
                    Card.deck_id.in_(deck_ids),
                    Card.original_deck_id.is_not(None),
                )
                .order_by(Card.id)
            ).all()
            if deck_ids
            else []
        )
        decks = (
            self.db.scalars(
                select(Deck)
                .where(Deck.collection_id == self.collection.id, Deck.id.in_(deck_ids))
                .order_by(Deck.id)
            ).all()
            if deck_ids
            else []
        )
        affected_notes = (
            self.db.scalars(
                select(Note)
                .where(Note.collection_id == self.collection.id, Note.id.in_(note_ids))
                .order_by(Note.id)
            ).all()
            if note_ids
            else []
        )
        self.media_cleanup_candidates.update(r.media_asset_id for r in refs)
        self.media_cleanup_candidates.update(
            a.media_asset_id for a in attempts if a.media_asset_id
        )
        facts = {
            "resource_updated": resource.updated_at,
            "revision": getattr(resource, "revision", None),
            "decks": [(d.id, d.updated_at) for d in decks],
            "notes": [(n.id, n.revision, n.updated_at) for n in affected_notes],
            "cards": [
                (c.id, c.deck_id, c.schedule_revision, c.updated_at) for c in cards
            ],
            "attempts": [(a.id, a.updated_at) for a in attempts],
            "references": [(r.id, r.media_asset_id) for r in refs],
            "returned_cards": [
                (c.id, c.original_deck_id, c.updated_at) for c in borrowed
            ],
        }
        impact = {
            "decks_deleted": len(deck_ids),
            "notes_deleted": len(note_ids),
            "cards_deleted": len(cards),
            "attempts_deleted": len(attempts),
            "media_references_deleted": len(refs),
            "cards_returned": len(borrowed),
        }
        return resource, cards, deck_ids, note_ids, facts, impact

    def deletion_preview(self, resource_type, resource_id):
        self.repo.lock()
        _, _, _, _, facts, impact = self.affected(resource_type, resource_id)
        token = confirmation.issue(
            "delete:" + resource_type, self.collection.id, resource_id, facts
        )
        return {"impact": impact, "confirmation_token": token}

    def delete_resource(self, resource_type, resource_id, token):
        self.repo.lock()
        resource, cards, deck_ids, note_ids, facts, impact = self.affected(
            resource_type, resource_id
        )
        confirmation.verify(
            token, "delete:" + resource_type, self.collection.id, resource_id, facts
        )
        if resource_type == "deck":
            borrowed = self.db.scalars(
                select(Card).where(
                    Card.collection_id == self.collection.id,
                    or_(
                        Card.deck_id.in_(deck_ids), Card.original_deck_id.in_(deck_ids)
                    ),
                    Card.original_deck_id.is_not(None),
                )
            ).all()
            for card in borrowed:
                card.deck_id, card.deck_kind, card.original_deck_id = (
                    card.original_deck_id,
                    "standard",
                    None,
                )
            self.db.flush()
        if cards:
            self.db.execute(
                delete(Card).where(
                    Card.collection_id == self.collection.id,
                    Card.id.in_([card.id for card in cards]),
                )
            )
        if resource_type == "note":
            self.db.delete(resource)
        elif resource_type == "deck":
            # Only the Library-sourced notes detected by the preview are removed.
            if note_ids:
                orphaned = self.db.scalars(
                    select(Note.id).where(
                        Note.collection_id == self.collection.id,
                        Note.id.in_(note_ids),
                        ~exists(
                            select(Card.id).where(
                                Card.collection_id == self.collection.id,
                                Card.note_id == Note.id,
                            )
                        ),
                    )
                ).all()
                if orphaned:
                    self.db.execute(
                        delete(Note).where(
                            Note.collection_id == self.collection.id,
                            Note.id.in_(orphaned),
                        )
                    )
            self.db.execute(
                delete(Deck).where(
                    Deck.collection_id == self.collection.id, Deck.id.in_(deck_ids)
                )
            )
        self.db.flush()
        self.cleanup_media()
        return {"deleted": True, "impact": impact}

    def type_preview(self, note_id, target_key):
        self.repo.lock()
        note = self.repo.get(Note, note_id)
        target = self.note_type(target_key)
        if target.id == note.note_type_id:
            raise DomainError(422, "NOTETYPE_UNCHANGED", "Choose a different NoteType.")
        source_fields, target_fields = (
            self.fields_for(note.note_type_id),
            self.fields_for(target.id),
        )
        source_keys = {field.key for field in source_fields}
        pairs = {
            "english": "word",
            "word": "english",
            "chinese": "meaning",
            "meaning": "chinese",
        }
        suggested = {
            field.key: field.key
            if field.key in source_keys
            else pairs.get(field.key)
            if pairs.get(field.key) in source_keys
            else None
            for field in target_fields
        }
        _, _, _, _, facts, impact = self.affected("note", note_id)
        impact["notes_deleted"] = 0
        templates = self.templates_for(target.id)
        suggested_values = {
            key: note.fields.get(source) for key, source in suggested.items() if source
        }
        impact["cards_created"] = sum(
            all(present(suggested_values.get(key)) for key in template.required_fields)
            for template in templates
        )
        impact["possible_cards_created"] = len(templates)
        return {
            "note_id": note.id,
            "revision": note.revision,
            "source_note_type": self.db.get(NoteType, note.note_type_id).key,
            "target_note_type": target.key,
            "source_fields": [
                {"key": f.key, "kind": f.kind, "required": f.required}
                for f in source_fields
            ],
            "target_fields": [
                {"key": f.key, "kind": f.kind, "required": f.required}
                for f in target_fields
            ],
            "target_templates": [
                {"key": t.key, "required_fields": t.required_fields}
                for t in self.templates_for(target.id)
            ],
            "suggested_field_mapping": suggested,
            "generation_basis": "suggested_field_mapping",
            "impact": impact,
            "confirmation_token": confirmation.issue(
                "notetype:" + target.key, self.collection.id, note.id, facts
            ),
        }

    def change_type(self, note_id, body):
        self.repo.lock()
        note, cards, _, _, facts, _ = self.affected("note", note_id)
        target = self.note_type(body.target_note_type_key)
        confirmation.verify(
            body.confirmation_token,
            "notetype:" + target.key,
            self.collection.id,
            note_id,
            facts,
            "NOTETYPE_CHANGE_CONFLICT",
        )
        if note.revision != body.revision:
            raise DomainError(
                409,
                "NOTETYPE_CHANGE_CONFLICT",
                "The Note revision has changed.",
                {"current_revision": note.revision},
            )
        if target.id == note.note_type_id:
            raise DomainError(422, "NOTETYPE_UNCHANGED", "Choose a different NoteType.")
        source_fields = {f.key: f for f in self.fields_for(note.note_type_id)}
        target_fields = {f.key: f for f in self.fields_for(target.id)}
        if set(body.field_mapping) != set(target_fields) or set(
            body.field_values
        ) - set(target_fields):
            raise DomainError(
                422,
                "NOTETYPE_FIELD_MAPPING_INVALID",
                "Confirm a mapping or null for every target field.",
            )
        values = {}
        for key, source in body.field_mapping.items():
            if source is not None:
                if (
                    source not in source_fields
                    or source_fields[source].kind != target_fields[key].kind
                ):
                    raise DomainError(
                        422,
                        "NOTETYPE_FIELD_MAPPING_INVALID",
                        "Field kinds are incompatible.",
                        {"field": key},
                    )
                values[key] = note.fields.get(source)
        values.update(body.field_values)
        fields, media = self.validate_fields(target.id, values, mapping=True)
        deck_id = body.deck_id
        if deck_id is None:
            old_decks = {card.deck_id for card in cards if card.deck_kind == "standard"}
            if len(old_decks) != 1 or any(
                card.deck_kind != "standard" for card in cards
            ):
                raise DomainError(
                    422, "TARGET_DECK_REQUIRED", "Select a destination Standard Deck."
                )
            deck_id = next(iter(old_decks))
        self.repo.standard_deck(deck_id)
        self.db.execute(
            delete(Card).where(
                Card.collection_id == self.collection.id, Card.note_id == note.id
            )
        )
        note.note_type_id, note.fields, note.revision = (
            target.id,
            fields,
            note.revision + 1,
        )
        self.db.flush()
        self.sync_media(note, media)
        generation = self.generate(note, deck_id)
        self.cleanup_media()
        return {**self.note_data(note), **generation}
