# Collection ownership and Library imports

Status: accepted

Each user owns exactly one Collection, enforced by a database uniqueness constraint. The system Library is one separate, read-only Collection with no user owner. Library import copies Decks and Notes into the user's Collection; imported Notes retain their Library `guid` so repeated imports are idempotent, but later imports never overwrite local edits. Shared reference media may remain shared in OSS, while user recordings remain Collection-private.

This gives the first version simple authorization and deletion semantics. Teacher access, shared user Collections, assignments, and automatic Library synchronization are deferred.
