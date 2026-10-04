import json
import logging
import sqlite3
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from tech_radar_agent.models import Article

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/tech_radar.db")

# Dates are stored as ISO 8601 text in UTC and `extra` / `interests` as JSON text: SQLite has no
# native type for either. The LLM columns stay NULL until the agent loop fills them in.
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
    summary        TEXT,
    reason         TEXT,
    interests      TEXT,
    scored_at      TEXT,
    scored_with    TEXT
)
"""

# Columns added after the first version of the table, in order. connect() adds the missing ones to an
# existing database, so an older data/tech_radar.db is upgraded in place without losing articles.
ADDED_COLUMNS = {
    "reason": "TEXT",  # One sentence: why the article matters (or not) to the reader.
    "interests": "TEXT",  # JSON list of profile interest ids.
    "scored_at": "TEXT",  # When the article was scored (ISO 8601, UTC).
    "scored_with": "TEXT",  # The model that scored it: scores depend on the model.
}


@dataclass(frozen=True)
class StoredArticle:
    """An article read back from the database, with the id needed to save results for it."""

    id: int
    article: Article


def connect(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open the database, creating its folder and the schema if needed, and upgrading an older schema."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row  # Rows can be read by column name: row["title"].
    conn.execute(SCHEMA)
    _add_missing_columns(conn)
    return conn


def _add_missing_columns(conn: sqlite3.Connection) -> None:
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(articles)")}
    with conn:
        for name, column_type in ADDED_COLUMNS.items():
            if name not in existing:
                # Names come from ADDED_COLUMNS above, never from outside: safe to put in the statement.
                conn.execute(f"ALTER TABLE articles ADD COLUMN {name} {column_type}")
                logger.info("Database upgraded: added column `%s`", name)


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


def fetch_articles_to_score(
    conn: sqlite3.Connection,
    max_age_days: int,
    limit: int,
    now: datetime | None = None,
) -> list[StoredArticle]:
    """Articles not scored yet and recent enough, newest first, at most `limit` of them.

    An article's age is taken from its publication date, or from its collection date when the source
    gives none. Older unscored articles are left alone for good: they will never reach a digest.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    rows = conn.execute(
        """
        SELECT id, source, title, url, author, content, published_at, fetched_at, extra
        FROM articles
        WHERE score IS NULL AND coalesce(published_at, fetched_at) >= ?
        ORDER BY coalesce(published_at, fetched_at) DESC, id DESC
        LIMIT ?
        """,
        (cutoff.isoformat(), limit),
    ).fetchall()

    articles = []
    for row in rows:
        try:
            articles.append(StoredArticle(id=row["id"], article=_to_article(row)))
        except (ValueError, TypeError) as error:  # A row that no longer passes Article's checks.
            logger.warning("Skipping stored article %s (%s)", row["id"], error)
    return articles


def _to_article(row: sqlite3.Row) -> Article:
    """Rebuild an Article from a row. Article re-validates it (URL scheme, text cleaning)."""
    extra = json.loads(row["extra"])
    return Article(
        source=row["source"],
        title=row["title"],
        url=row["url"],
        author=row["author"],
        content=row["content"],
        published_at=datetime.fromisoformat(row["published_at"]) if row["published_at"] else None,
        fetched_at=datetime.fromisoformat(row["fetched_at"]),
        extra=extra if isinstance(extra, dict) else {},
    )


def save_score(
    conn: sqlite3.Connection,
    article_id: int,
    *,
    score: int,
    reason: str,
    interests: Sequence[str],
    scored_with: str,
    scored_at: datetime | None = None,
) -> None:
    """Store the result of scoring one article. Committed right away: a later crash loses nothing."""
    with conn:
        conn.execute(
            """
            UPDATE articles
            SET score = ?, reason = ?, interests = ?, scored_at = ?, scored_with = ?
            WHERE id = ?
            """,
            (
                score,
                reason,
                json.dumps(list(interests)),
                (scored_at or datetime.now(timezone.utc)).isoformat(),
                scored_with,
                article_id,
            ),
        )


def save_summary(conn: sqlite3.Connection, article_id: int, summary: str) -> None:
    """Store the summary of one article. Committed right away."""
    with conn:
        conn.execute("UPDATE articles SET summary = ? WHERE id = ?", (summary, article_id))
