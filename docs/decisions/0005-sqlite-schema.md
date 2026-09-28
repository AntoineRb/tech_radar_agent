# 0005. SQLite schema and type mapping

- Status: Accepted
- Date: 2026-09-28

## Context

SQLite only has `INTEGER`, `REAL`, `TEXT`, `BLOB` and `NULL`, but `Article` contains `datetime` values and a `dict`. The LLM columns will be filled in later, and the local database must not need a migration when that happens.

## Decision

- A single `articles` table, created with `CREATE TABLE IF NOT EXISTS` when the connection opens.
- Dates are stored as ISO 8601 `TEXT`, and `extra` as JSON `TEXT`.
- `score INTEGER` (0–10) and `summary TEXT` are created now. They stay `NULL` until the LLM processes the article.
- Articles are inserted with `INSERT OR IGNORE`, so a duplicate `normalized_url` is skipped silently.
- `connect()` creates the `data/` folder if it is missing (as a safeguard, in addition to `.gitkeep`).
- The standard library `sqlite3` module is used, with no ORM.

## Consequences

- `WHERE score IS NULL` gives the articles still waiting to be processed.
- Date text sorts in the right order only if every date uses the same offset. Collectors should produce UTC datetimes.
- The status column (sent or not sent) is not included yet. It will be added in step 3 with `ALTER TABLE … ADD COLUMN`.
