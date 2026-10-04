# 0020. Storing results: four new columns, the model recorded, in-place schema upgrade

- Status: Accepted
- Date: 2026-10-04

## Context

Scores and summaries must be stored for the digest and, later, for feedback. The local database already holds collected articles: adding columns must not lose them.

## Decision

- New columns in `articles`: `reason` (text), `interests` (JSON list of profile ids), `scored_at` (ISO 8601, UTC) and `scored_with` (the model that scored the article). `score` and `summary` already existed.
- `scored_with` is stored because scores depend on the model: after a model change, it tells which scores to compare or redo.
- `connect()` adds missing columns with `ALTER TABLE … ADD COLUMN` (listed in `ADDED_COLUMNS`): an existing database is upgraded in place, and each added column is logged once.
- `fetch_articles_to_score`, `save_score` and `save_summary` are the only entry points. Each save is committed at once, so a crash loses nothing already done. A stored row that no longer passes `Article`'s checks is skipped and logged.

## Consequences

- Checked on a copy of a real database: 276 articles kept, 4 columns added.
- No migration tool is needed for now; a "sent" status for the digest will be added the same way.
