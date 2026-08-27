# Filtered Decks and runtime review queues

Status: accepted

Filtered Decks temporarily move Cards from their Standard Deck, retaining original placement data so Cards can be returned without a separate membership table. A Card can be in at most one Filtered Deck at a time. Review queues are runtime state: the system may keep a short-lived Card ID queue in memory or Redis and rebuild it when lost; it does not persist a Study Session or queue table. Card content remains dynamically rendered from the current Note and Card Template.

Filtered Deck search terms define the query, limit, and sort order. Rebuilding creates an ordered runtime Card ID queue whose main order remains stable for that build; intraday learning Cards may be reinserted by due time. Unlike Anki's persisted `due`/`odue` position encoding, LanGear does not write filtered positions or original due values to Cards. Formal scheduling fields remain unchanged until an answer actually reschedules the Card.

Version 1 always reschedules Cards reviewed in a Filtered Deck. It does not expose preview mode or persist the `preview_repeat` queue.

The Card stores Anki-style `type` and `queue` values, including negative queue values for suspended and buried states. Collection time zones determine study-day boundaries; absolute timestamps are stored as UTC PostgreSQL `timestamptz` values.
