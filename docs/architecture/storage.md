# Storage

Defined in [`src/tech_radar_agent/storage/database.py`](../../src/tech_radar_agent/storage/database.py). SQLite is the agent's memory: it remembers every article it has seen, and later it will also store scores, summaries and what has already been sent.

## Location

The default database is `data/tech_radar.db`, relative to the directory the agent is launched from. `connect()` creates the `data/` folder if it is missing. The `*.db` files are git-ignored.

## Schema

```sql
CREATE TABLE IF NOT EXISTS articles (
    id             INTEGER PRIMARY KEY,
    normalized_url TEXT    NOT NULL UNIQUE,
    url            TEXT    NOT NULL,
    source         TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    author         TEXT,
    content        TEXT,
    published_at   TEXT,
    fetched_at     TEXT    NOT NULL,
    extra          TEXT    NOT NULL DEFAULT '{}',
    score          INTEGER,
    summary        TEXT,
    reason         TEXT,
    interests      TEXT,
    scored_at      TEXT,
    scored_with    TEXT
)
```

| Python type | Stored as | Why |
|---|---|---|
| `datetime` | `TEXT`, ISO 8601 (`2026-09-01T00:00:00+00:00`) | Easy to read, and text order matches time order |
| `dict` (`extra`), `list` (`interests`) | `TEXT`, JSON | SQLite has no native map or list type |
| `None` | `NULL` | |

The LLM columns stay `NULL` until the agent loop fills them in:

| Column | Content |
|---|---|
| `score` | 0-10, see [scoring](scoring.md) |
| `reason` | one sentence: why the article matters (or not) to the reader |
| `interests` | JSON list of profile interest ids, e.g. `["ai-agents", "python"]` |
| `scored_at` | when it was scored (ISO 8601, UTC) |
| `scored_with` | the model that scored it, e.g. `qwen3.6:latest`. Scores depend on the model: this tells which ones to compare or redo after a model change |
| `summary` | only for articles scored at or above the threshold, with enough content; `NULL` otherwise |
| `sent_at` | when the article went out in a digest (ISO 8601, UTC); `NULL` while it has not been sent |

An unscored article is not always waiting: articles older than the scoring window are never scored and keep `score = NULL` for good. Articles to process are those returned by `fetch_articles_to_score`.

### Schema upgrades

`reason`, `interests`, `scored_at`, `scored_with` and `sent_at` were added after the first version of the table. `connect()` adds any missing column with `ALTER TABLE … ADD COLUMN` (listed in `ADDED_COLUMNS`), so an existing database is upgraded in place, without losing articles, and each added column is logged once.

See [ADR 0005](../decisions/0005-sqlite-schema.md) for the reasoning behind these choices.

## API

```python
from tech_radar_agent.storage import (
    best_recent_score, connect, fetch_articles_to_score, fetch_digest_candidates, mark_sent,
    save_articles, save_score, save_summary,
)

conn = connect()                          # opens data/tech_radar.db, creates or upgrades it if needed
added = save_articles(conn, articles)     # returns the number of new rows
for stored in fetch_articles_to_score(conn, max_age_days=3, limit=100):
    stored.id, stored.article             # the row id, and the Article rebuilt from the row
    save_score(conn, stored.id, score=9, reason="…", interests=["python"], scored_with="qwen3.6:latest")
    save_summary(conn, stored.id, "…")
for candidate in fetch_digest_candidates(conn, min_score=8, max_age_days=3):
    candidate.article, candidate.score, candidate.reason, candidate.interests, candidate.summary
mark_sent(conn, [candidate.id for candidate in chosen])   # once the digest was delivered
best_recent_score(conn, max_age_days=3)   # for the report of a day with no candidate
row = conn.execute("SELECT * FROM articles").fetchone()
row["title"]                              # rows can be read by column name
```

| Function | Behavior |
|---|---|
| `connect(db_path=DEFAULT_DB_PATH)` | Creates the parent folder and the `articles` table if needed, and adds missing columns to an older table. Returns a connection whose rows are `sqlite3.Row`. |
| `save_articles(conn, articles)` | Inserts all articles in one transaction with `INSERT OR IGNORE`. Articles whose `normalized_url` is already stored are skipped silently. Returns how many were actually added. |
| `fetch_articles_to_score(conn, max_age_days, limit, now=None)` | Unscored articles whose publication date (or collection date, if there is none) is within `max_age_days`, newest first, at most `limit`. Returns `StoredArticle(id, article)` items. A row that no longer passes `Article`'s checks is logged and skipped. |
| `save_score(conn, article_id, *, score, reason, interests, scored_with, scored_at=None)` | Stores one scoring result. `scored_at` defaults to now (UTC). |
| `save_summary(conn, article_id, summary)` | Stores one summary. |
| `fetch_digest_candidates(conn, min_score, max_age_days, now=None)` | Articles scored at least `min_score`, not sent yet, within the same age window as scoring, in selection order: best score first, then **oldest first** on equal scores ([ADR 0023](../decisions/0023-digest-selection.md)). Returns `DigestCandidate(id, article, score, reason, interests, summary)`; `summary` is `None` when there is none. A row that no longer passes the checks is logged and skipped. |
| `mark_sent(conn, article_ids, sent_at=None)` | Marks a whole digest as sent in one transaction (all or none). `sent_at` defaults to now (UTC). Call it only once the digest was delivered. |
| `best_recent_score(conn, max_age_days, now=None)` | Highest score among recent articles not sent yet, or `None`. Shown in the report of a day with no candidate. |

Every save is committed right away, so a crash in the middle of a run loses nothing already done.

## Planned

- Purging old articles automatically, keeping those with reader feedback.
