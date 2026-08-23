# Explicit destructive deletion

Status: accepted

Deck, Note, Card, and NoteType deletion are hard-delete operations after an explicit confirmation. Deleting a Card removes its Attempts but keeps its Note and sibling Cards. Deleting a Note removes its Cards and Attempts. Deleting a Standard Deck removes its Cards while retaining Notes that still have any Card; deleting a Filtered Deck first returns its Cards. Deleting a NoteType/Card Template removes the affected Cards and Attempts after showing the impact. There is no first-version recycle bin; PostgreSQL backup/PITR and delayed OSS cleanup are the recovery safeguards.
