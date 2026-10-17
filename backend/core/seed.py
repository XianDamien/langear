"""Versioned, idempotent system definitions. Never overwrite user content."""

from sqlalchemy import select
from core.models import Collection, NoteType, NoteTypeField, CardTemplate

DEFINITIONS = {
    "vocabulary": {
        "name": "Vocabulary",
        "fields": [
            ("word", "text", True),
            ("meaning", "text", False),
            ("phonetic", "text", False),
            ("note", "text", False),
            ("reference_audio", "audio", False),
            ("image", "image", False),
            ("mnemonic", "text", False),
        ],
        "templates": [
            (
                "vocabulary_english_to_chinese",
                ["word", "meaning"],
                ["word"],
                ["meaning", "word", "phonetic", "reference_audio", "image", "mnemonic", "note"],
                "meaning",
                "none",
            ),
            (
                "vocabulary_chinese_to_english",
                ["word", "meaning"],
                ["meaning"],
                ["word", "meaning", "phonetic", "reference_audio", "image", "mnemonic", "note"],
                "word",
                "none",
            ),
        ],
    },
    "sentence": {
        "name": "Sentence",
        "fields": [
            ("english", "text", True),
            ("chinese", "text", False),
            ("note", "text", False),
            ("reference_audio", "audio", False),
        ],
        "templates": [
            (
                "sentence_retelling",
                ["english", "reference_audio"],
                ["reference_audio"],
                ["reference_audio", "english", "chinese", "note"],
                "english",
                "audio",
            ),
            (
                "sentence_translation",
                ["english", "chinese"],
                ["chinese"],
                ["english", "chinese", "reference_audio", "note"],
                "english",
                "text",
            ),
            (
                "sentence_dictation",
                ["english", "reference_audio"],
                ["reference_audio"],
                ["english", "chinese", "note"],
                "english",
                "text",
            ),
        ],
    },
}


def seed_system(db):
    if db.scalar(select(Collection).where(Collection.kind == "library")) is None:
        db.add(Collection(kind="library", timezone="UTC"))
    for key, spec in DEFINITIONS.items():
        nt = db.scalar(select(NoteType).where(NoteType.key == key))
        if nt is None:
            nt = NoteType(key=key, display_name=spec["name"])
            db.add(nt)
            db.flush()
        for order, (name, kind, required) in enumerate(spec["fields"]):
            if (
                db.scalar(
                    select(NoteTypeField).where(
                        NoteTypeField.note_type_id == nt.id, NoteTypeField.key == name
                    )
                )
                is None
            ):
                db.add(
                    NoteTypeField(
                        note_type_id=nt.id,
                        key=name,
                        kind=kind,
                        required=required,
                        ord=order,
                    )
                )
        for order, (name, required, front, back, answer, input_type) in enumerate(
            spec["templates"]
        ):
            if db.scalar(select(CardTemplate).where(CardTemplate.key == name)) is None:
                db.add(
                    CardTemplate(
                        note_type_id=nt.id,
                        key=name,
                        ord=order,
                        required_fields=required,
                        q_format=front,
                        a_format=back,
                        answer_field=answer,
                        input_type=input_type,
                    )
                )
    db.flush()
