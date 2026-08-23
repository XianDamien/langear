# Filtered Decks and runtime review queues

Status: accepted

Filtered Decks temporarily move Cards from their Standard Deck, retaining original placement data so Cards can be returned without a separate membership table. A Card can be in at most one Filtered Deck at a time. Review queues are runtime state: the system may keep a short-lived Card ID queue in memory or Redis and rebuild it when lost; it does not persist a Study Session or queue table. Card content remains dynamically rendered from the current Note and Card Template.

The Card stores Anki-style `type` and `queue` values, including negative queue values for suspended and buried states. Collection time zones determine study-day boundaries; absolute timestamps are stored as UTC PostgreSQL `timestamptz` values.
