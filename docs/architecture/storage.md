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

An unscored article is not always waiting: articles older than the scoring window are never scored and keep `score = NULL` for good. Articles to process are those returned by `fetch_articles_to_score`.

### Schema upgrades

`reason`, `interests`, `scored_at` and `scored_with` were added after the first version of the table. `connect()` adds any missing column with `ALTER TABLE … ADD COLUMN` (listed in `ADDED_COLUMNS`), so an existing database is upgraded in place, without losing articles, and each added column is logged once.

See [ADR 0005](../decisions/0005-sqlite-schema.md) for the reasoning behind these choices.

## API

```python
from tech_radar_agent.storage import connect, fetch_articles_to_score, save_articles, save_score, save_summary

conn = connect()                          # opens data/tech_radar.db, creates or upgrades it if needed
added = save_articles(conn, articles)     # returns the number of new rows
for stored in fetch_articles_to_score(conn, max_age_days=3, limit=100):
    stored.id, stored.article             # the row id, and the Article rebuilt from the row
    save_score(conn, stored.id, score=9, reason="…", interests=["python"], scored_with="qwen3.6:latest")
    save_summary(conn, stored.id, "…")
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

Every save is committed right away, so a crash in the middle of a run loses nothing already done.

## Planned

- A status column (sent or not sent) for the digest, added like the scoring columns (`ADDED_COLUMNS`).
- Purging old articles automatically, keeping those with reader feedback.
