# PostgreSQL and UUIDv7

Status: accepted

PostgreSQL is the database for development, staging, and production; schema capabilities are designed for PostgreSQL rather than SQLite. Core entities use application-generated UUIDv7 identifiers. Core private tables carry `collection_id`, and composite foreign keys enforce that Notes, Cards, Decks, Attempts, and media references stay within one Collection.

Production uses explicit migration jobs, automated PostgreSQL backups with WAL/PITR, and isolated databases/OSS namespaces per environment. The first version does not enable PostgreSQL Row-Level Security; Collection-scoped application modules and database constraints provide the initial isolation layer.
