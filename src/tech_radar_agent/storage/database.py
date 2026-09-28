import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path

from tech_radar_agent.models import Article

DEFAULT_DB_PATH = Path("data/tech_radar.db")

# Dates are stored as ISO 8601 text and `extra` as JSON text: SQLite has no native type for either.
# `score` and `summary` stay NULL until the LLM loop fills them in.
SCHEMA = """
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
"""


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database, creating its folder and the schema if they don't exist yet."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Rows can be read by column name: row["title"].
    conn.execute(SCHEMA)
    return conn


def save_articles(conn: sqlite3.Connection, articles: Iterable[Article]) -> int:
    """Insert new articles, silently skipping already known URLs. Return how many were added."""
    rows = [
        (
            article.normalized_url,
            article.url,
            article.source,
            article.title,
            article.author,
            article.content,
            article.published_at.isoformat() if article.published_at else None,
            article.fetched_at.isoformat(),
            json.dumps(article.extra, default=str),
        )
        for article in articles
    ]
    with conn:  # One transaction: all rows are committed together.
        cursor = conn.executemany(
            """
            INSERT OR IGNORE INTO articles (
                normalized_url, url, source, title, author,
                content, published_at, fetched_at, extra
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
    return cursor.rowcount
