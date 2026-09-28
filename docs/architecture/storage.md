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
    summary        TEXT
)
```

| Python type | Stored as | Why |
|---|---|---|
| `datetime` | `TEXT`, ISO 8601 (`2026-09-01T00:00:00+00:00`) | Easy to read, and text order matches time order |
| `dict` (`extra`) | `TEXT`, JSON | SQLite has no native map type |
| `None` | `NULL` | |

`score` (0–10) and `summary` stay `NULL` until the LLM loop fills them in. So articles still waiting to be processed are the rows `WHERE score IS NULL`.

See [ADR 0005](../decisions/0005-sqlite-schema.md) for the reasoning behind these choices.

## API

```python
from tech_radar_agent.storage import connect, save_articles

conn = connect()                          # opens data/tech_radar.db, creates it if needed
added = save_articles(conn, articles)     # returns the number of new rows
row = conn.execute("SELECT * FROM articles").fetchone()
row["title"]                              # rows can be read by column name
```

| Function | Behavior |
|---|---|
| `connect(db_path=DEFAULT_DB_PATH)` | Creates the parent folder and the `articles` table if needed. Returns a connection whose rows are `sqlite3.Row`. |
| `save_articles(conn, articles)` | Inserts all articles in one transaction with `INSERT OR IGNORE`. Articles whose `normalized_url` is already stored are skipped silently. Returns how many were actually added. |

## Planned

- A status column (sent or not sent) for the digest, added in step 3 with `ALTER TABLE … ADD COLUMN`.
- Queries for the scoring loop: fetch unscored articles, write the score and summary back.
