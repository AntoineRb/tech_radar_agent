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
    scored_with    TEXT,
    sent_at        TEXT
)
"""

# Columns added after the first version of the table, in order. connect() adds the missing ones to an
# existing database, so an older data/tech_radar.db is upgraded in place without losing articles.
ADDED_COLUMNS = {
    "reason": "TEXT",  # One sentence: why the article matters (or not) to the reader.
    "interests": "TEXT",  # JSON list of profile interest ids.
    "scored_at": "TEXT",  # When the article was scored (ISO 8601, UTC).
    "scored_with": "TEXT",  # The model that scored it: scores depend on the model.
    "sent_at": "TEXT",  # When the article went out in a digest (ISO 8601, UTC). NULL: not sent yet.
}


@dataclass(frozen=True)
class StoredArticle:
    """An article read back from the database, with the id needed to save results for it."""

    id: int
    article: Article


@dataclass(frozen=True)
class DigestCandidate:
    """A scored article that may go into a digest: the article and what the LLM said about it."""

    id: int
    article: Article
    score: int
    reason: str
    interests: tuple[str, ...]  # Profile interest ids, possibly empty.
    summary: str | None  # None: too little text to summarize, or the summary failed.


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


def fetch_digest_candidates(
    conn: sqlite3.Connection,
    min_score: int,
    max_age_days: int,
    now: datetime | None = None,
) -> list[DigestCandidate]:
    """Articles that may go into the next digest, in selection order.

    Scored at least `min_score`, not sent yet, and recent enough (same age rule as
    fetch_articles_to_score). Best score first; on equal scores, the OLDEST first: it leaves the age
    window sooner, so it gets its chance before newer articles that can still wait.
    Articles left out of a digest stay unsent, so they compete again for the next one.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    rows = conn.execute(
        """
        SELECT id, source, title, url, author, content, published_at, fetched_at, extra,
               score, reason, interests, summary
        FROM articles
        WHERE score >= ? AND sent_at IS NULL AND coalesce(published_at, fetched_at) >= ?
        ORDER BY score DESC, coalesce(published_at, fetched_at) ASC, id ASC
        """,
        (min_score, cutoff.isoformat()),
    ).fetchall()

    candidates = []
    for row in rows:
        try:
            candidates.append(_to_candidate(row))
        except (ValueError, TypeError) as error:  # A row that no longer passes the checks.
            logger.warning("Skipping stored article %s (%s)", row["id"], error)
    return candidates


def _to_candidate(row: sqlite3.Row) -> DigestCandidate:
    interests = json.loads(row["interests"] or "[]")
    if not isinstance(interests, list) or not all(isinstance(item, str) for item in interests):
        raise ValueError("interests is not a list of ids")
    if not isinstance(row["reason"], str):
        raise ValueError("reason is missing")
    return DigestCandidate(
        id=row["id"],
        article=_to_article(row),
        score=row["score"],
        reason=row["reason"],
        interests=tuple(interests),
        summary=row["summary"],
    )


def best_recent_score(conn: sqlite3.Connection, max_age_days: int, now: datetime | None = None) -> int | None:
    """The highest score among recent articles not sent yet, or None if none is scored.

    Shown in the report of a day with no digest candidate: days in a row just under the threshold
    hint that the threshold is too high for the model.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=max_age_days)
    row = conn.execute(
        "SELECT max(score) FROM articles WHERE sent_at IS NULL AND coalesce(published_at, fetched_at) >= ?",
        (cutoff.isoformat(),),
    ).fetchone()
    return row[0]


def mark_sent(conn: sqlite3.Connection, article_ids: Iterable[int], sent_at: datetime | None = None) -> None:
    """Record that these articles went out in a digest, so they are never sent again.

    One transaction: either every article of the digest is marked, or none is. Call it only once
    the digest was actually delivered.
    """
    when = (sent_at or datetime.now(timezone.utc)).isoformat()
    with conn:
        conn.executemany(
            "UPDATE articles SET sent_at = ? WHERE id = ?", [(when, article_id) for article_id in article_ids]
        )
