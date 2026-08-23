# Anki-style content model

Status: accepted

LanGear uses Anki's separation of content and presentation: a Note belongs to a Collection and a NoteType, while persistent Cards are generated from Card Templates and independently belong to Decks and FSRS schedules. A Note has no Deck ownership, so Cards rendered from one Note may be moved into different or mixed-content Decks. This supports composition and avoids making a course-completion lifecycle the center of the product.

The first version provides system-managed Vocabulary and Sentence NoteTypes. Users can edit Note fields but cannot edit NoteTypes or Card Templates.
