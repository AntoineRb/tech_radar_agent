# 0004. Keep source-specific data in an `extra` dict

- Status: Accepted
- Date: 2026-09-28

## Context

Each source has its own metadata: Hacker News points and comment count, GitHub stars and language, arXiv categories. Adding a field for each one would clutter the shared model.

## Decision

`Article` has an `extra: dict[str, Any]` field, empty by default. It is stored as JSON text in the database.

## Consequences

- New sources can be added without changing the model or the schema.
- The keys of `extra` are not validated, and they are hard to query in SQL (only through SQLite's `json_extract`).
