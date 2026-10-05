import json
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tech_radar_agent.models import Article
from tech_radar_agent.storage import (
    best_recent_score,
    connect,
    fetch_articles_to_score,
    fetch_digest_candidates,
    mark_sent,
    save_articles,
    save_score,
    save_summary,
)


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    yield connection
    connection.close()


def make_article(url: str = "https://example.com/a", **overrides) -> Article:
    return Article(**({"source": "test", "title": "A title", "url": url} | overrides))


def rows(conn) -> list[dict]:
    return [dict(row) for row in conn.execute("SELECT * FROM articles ORDER BY id")]


def test_connect_creates_missing_folders(tmp_path):
    db_path = tmp_path / "nested" / "data" / "test.db"
    connect(db_path).close()
    assert db_path.exists()


def test_connect_twice_keeps_existing_data(tmp_path):
    db_path = tmp_path / "test.db"
    first = connect(db_path)
    save_articles(first, [make_article()])
    first.close()
    second = connect(db_path)
    assert len(rows(second)) == 1
    second.close()


def test_rows_can_be_read_by_column_name(conn):
    save_articles(conn, [make_article()])
    assert conn.execute("SELECT title FROM articles").fetchone()["title"] == "A title"


def test_save_returns_number_of_new_articles(conn):
    articles = [make_article("https://example.com/a"), make_article("https://example.com/b")]
    assert save_articles(conn, articles) == 2


def test_save_nothing(conn):
    assert save_articles(conn, []) == 0


def test_same_article_twice_is_ignored(conn):
    save_articles(conn, [make_article()])
    assert save_articles(conn, [make_article()]) == 0
    assert len(rows(conn)) == 1


def test_duplicates_are_detected_by_normalized_url(conn):
    first = make_article("https://example.com/a", source="hackernews")
    same_page = make_article("https://Example.com/a/?utm_source=rss", source="rss")
    assert save_articles(conn, [first, same_page]) == 1
    assert rows(conn)[0]["source"] == "hackernews"  # The first one seen is kept.


def test_all_fields_are_stored(conn):
    published = datetime(2026, 9, 1, 12, 30, tzinfo=timezone.utc)
    article = make_article(
        "https://Example.com/a?utm_source=x",
        source="hackernews",
        author="alice",
        content="Some text",
        published_at=published,
        extra={"points": 42, "tags": ["ai"]},
    )
    save_articles(conn, [article])

    row = rows(conn)[0]
    assert row["normalized_url"] == "https://example.com/a"
    assert row["url"] == "https://Example.com/a?utm_source=x"
    assert row["source"] == "hackernews"
    assert row["title"] == "A title"
    assert row["author"] == "alice"
    assert row["content"] == "Some text"
    assert datetime.fromisoformat(row["published_at"]) == published
    assert datetime.fromisoformat(row["fetched_at"]) == article.fetched_at
    assert json.loads(row["extra"]) == {"points": 42, "tags": ["ai"]}


def test_optional_fields_are_null(conn):
    save_articles(conn, [make_article()])
    row = rows(conn)[0]
    assert row["author"] is None
    assert row["content"] is None
    assert row["published_at"] is None
    assert row["extra"] == "{}"


def test_llm_columns_start_empty(conn):
    save_articles(conn, [make_article()])
    row = rows(conn)[0]
    assert row["score"] is None
    assert row["summary"] is None
    assert row["sent_at"] is None


def test_extra_values_that_are_not_json_are_stored_as_text(conn):
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    save_articles(conn, [make_article(extra={"seen": when})])
    assert json.loads(rows(conn)[0]["extra"]) == {"seen": str(when)}


# --- Schema upgrade ---

OLD_SCHEMA = """
CREATE TABLE articles (
    id INTEGER PRIMARY KEY, normalized_url TEXT NOT NULL UNIQUE, url TEXT NOT NULL, source TEXT NOT NULL,
    title TEXT NOT NULL, author TEXT, content TEXT, published_at TEXT, fetched_at TEXT NOT NULL,
    extra TEXT NOT NULL DEFAULT '{}', score INTEGER, summary TEXT
)
"""


def columns(conn) -> list[str]:
    return [row["name"] for row in conn.execute("PRAGMA table_info(articles)")]


def test_new_database_has_every_column(conn):
    assert {"reason", "interests", "scored_at", "scored_with", "sent_at"} <= set(columns(conn))


def test_old_database_is_upgraded_without_losing_articles(tmp_path, caplog):
    db_path = tmp_path / "old.db"
    old = sqlite3.connect(db_path)
    old.execute(OLD_SCHEMA)
    old.execute(
        "INSERT INTO articles (normalized_url, url, source, title, fetched_at) VALUES (?, ?, ?, ?, ?)",
        ("https://example.com/a", "https://example.com/a", "rss", "Kept", "2026-09-28T10:00:00+00:00"),
    )
    old.commit()
    old.close()

    with caplog.at_level("INFO"):
        upgraded = connect(db_path)
    assert {"reason", "interests", "scored_at", "scored_with", "sent_at"} <= set(columns(upgraded))
    assert rows(upgraded)[0]["title"] == "Kept"
    assert rows(upgraded)[0]["sent_at"] is None
    assert "added column `reason`" in caplog.text
    upgraded.close()


def test_upgrade_runs_only_once(tmp_path):
    db_path = tmp_path / "test.db"
    connect(db_path).close()
    second = connect(db_path)  # Would fail with "duplicate column" if columns were added again.
    assert columns(second).count("reason") == 1
    second.close()


# --- fetch_articles_to_score ---

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)


def published(days_ago: float) -> datetime:
    return NOW - timedelta(days=days_ago)


def add(conn, url: str, **fields) -> int:
    save_articles(conn, [make_article(url, **fields)])
    return conn.execute("SELECT id FROM articles WHERE url = ?", (url,)).fetchone()["id"]


def to_score(conn, max_age_days=3, limit=100) -> list[str]:
    return [stored.article.url for stored in fetch_articles_to_score(conn, max_age_days, limit, now=NOW)]


def test_fetch_returns_recent_unscored_articles_newest_first(conn):
    add(conn, "https://example.com/old", published_at=published(10))
    add(conn, "https://example.com/day1", published_at=published(1))
    add(conn, "https://example.com/hour", published_at=published(0.05))
    add(conn, "https://example.com/day2", published_at=published(2))
    assert to_score(conn) == ["https://example.com/hour", "https://example.com/day1", "https://example.com/day2"]


def test_fetch_skips_scored_articles(conn):
    article_id = add(conn, "https://example.com/a", published_at=published(1))
    add(conn, "https://example.com/b", published_at=published(1))
    save_score(conn, article_id, score=5, reason="ok", interests=[], scored_with="m")
    assert to_score(conn) == ["https://example.com/b"]


def test_fetch_uses_the_collection_date_when_there_is_no_publication_date(conn):
    add(conn, "https://example.com/recent", published_at=None, fetched_at=published(1))
    add(conn, "https://example.com/old", published_at=None, fetched_at=published(5))
    assert to_score(conn) == ["https://example.com/recent"]


def test_fetch_window_and_limit(conn):
    for day in range(6):
        add(conn, f"https://example.com/{day}", published_at=published(day + 0.5))
    assert len(to_score(conn, max_age_days=3)) == 3
    assert to_score(conn, max_age_days=3, limit=2) == ["https://example.com/0", "https://example.com/1"]


def test_fetch_rebuilds_full_articles_with_their_id(conn):
    article_id = add(
        conn, "https://example.com/a", source="github", author="alice", content="Text",
        published_at=published(1), extra={"stars": 3, "topics": ["llm"]},
    )
    [stored] = fetch_articles_to_score(conn, 3, 100, now=NOW)
    assert stored.id == article_id
    assert (stored.article.source, stored.article.author, stored.article.content) == ("github", "alice", "Text")
    assert stored.article.published_at == published(1)
    assert stored.article.extra == {"stars": 3, "topics": ["llm"]}


def test_fetch_skips_rows_that_are_no_longer_valid(conn, caplog):
    add(conn, "https://example.com/good", published_at=published(1))
    bad_id = add(conn, "https://example.com/bad", published_at=published(1))
    with conn:  # Simulate a row corrupted outside the agent.
        conn.execute("UPDATE articles SET url = 'javascript:alert(1)' WHERE id = ?", (bad_id,))
    assert to_score(conn) == ["https://example.com/good"]
    assert f"Skipping stored article {bad_id}" in caplog.text


def test_fetch_without_now_uses_the_current_time(conn):
    add(conn, "https://example.com/a", published_at=datetime.now(timezone.utc))
    assert len(fetch_articles_to_score(conn, 3, 100)) == 1


# --- save_score / save_summary ---


def test_save_score(conn):
    article_id = add(conn, "https://example.com/a")
    save_score(conn, article_id, score=9, reason="Très utile.", interests=("ai-agents", "python"),
               scored_with="qwen3.6:latest", scored_at=NOW)
    row = rows(conn)[0]
    assert row["score"] == 9
    assert row["reason"] == "Très utile."
    assert json.loads(row["interests"]) == ["ai-agents", "python"]
    assert datetime.fromisoformat(row["scored_at"]) == NOW
    assert row["scored_with"] == "qwen3.6:latest"
    assert row["summary"] is None  # Not touched.


def test_save_score_defaults_to_now_in_utc(conn):
    article_id = add(conn, "https://example.com/a")
    save_score(conn, article_id, score=1, reason="x", interests=[], scored_with="m")
    assert datetime.fromisoformat(rows(conn)[0]["scored_at"]).tzinfo == timezone.utc


def test_save_summary(conn):
    article_id = add(conn, "https://example.com/a")
    save_summary(conn, article_id, "Un résumé.")
    assert rows(conn)[0]["summary"] == "Un résumé."


def test_saves_only_touch_their_article(conn):
    first = add(conn, "https://example.com/a")
    add(conn, "https://example.com/b")
    save_score(conn, first, score=7, reason="x", interests=[], scored_with="m")
    save_summary(conn, first, "s")
    other = rows(conn)[1]
    assert other["score"] is None and other["summary"] is None


def test_saves_are_committed_immediately(tmp_path):
    db_path = tmp_path / "test.db"
    writer = connect(db_path)
    article_id = add(writer, "https://example.com/a")
    save_score(writer, article_id, score=8, reason="x", interests=[], scored_with="m")
    reader = sqlite3.connect(db_path)  # Another connection sees it without writer.commit().
    assert reader.execute("SELECT score FROM articles").fetchone()[0] == 8
    reader.close()
    writer.close()



# --- Digest: fetch_digest_candidates, best_recent_score, mark_sent ---


def scored(conn, url: str, score: int, days_ago: float = 1, summary: str | None = None, **fields) -> int:
    """Store a recent article with a score (and a summary if given). Return its id."""
    article_id = add(conn, url, published_at=published(days_ago), **fields)
    save_score(conn, article_id, score=score, reason=f"Reason {score}.", interests=["python"], scored_with="m")
    if summary is not None:
        save_summary(conn, article_id, summary)
    return article_id


def candidates(conn, min_score=8, max_age_days=3) -> list[str]:
    return [c.article.url for c in fetch_digest_candidates(conn, min_score, max_age_days, now=NOW)]


def test_candidates_are_scored_at_least_min_score(conn):
    scored(conn, "https://example.com/seven", 7)
    scored(conn, "https://example.com/eight", 8)  # Equal to the threshold: included.
    scored(conn, "https://example.com/ten", 10)
    add(conn, "https://example.com/unscored", published_at=published(1))
    assert candidates(conn) == ["https://example.com/ten", "https://example.com/eight"]


def test_candidates_best_score_first_then_oldest_first(conn):
    scored(conn, "https://example.com/8-new", 8, days_ago=0.1)
    scored(conn, "https://example.com/9", 9, days_ago=1)
    scored(conn, "https://example.com/8-old", 8, days_ago=2.5)  # Leaves the window soonest.
    scored(conn, "https://example.com/8-mid", 8, days_ago=1.5)
    assert candidates(conn) == [
        "https://example.com/9",
        "https://example.com/8-old",
        "https://example.com/8-mid",
        "https://example.com/8-new",
    ]


def test_candidates_keep_insertion_order_on_full_ties(conn):
    first = scored(conn, "https://example.com/a", 8, days_ago=1)
    second = scored(conn, "https://example.com/b", 8, days_ago=1)
    assert [c.id for c in fetch_digest_candidates(conn, 8, 3, now=NOW)] == [first, second]


def test_candidates_respect_the_age_window(conn):
    scored(conn, "https://example.com/recent", 9, days_ago=2)
    scored(conn, "https://example.com/old", 10, days_ago=4)
    scored(conn, "https://example.com/no-date", 9, days_ago=0)
    with conn:  # No publication date: the collection date counts, like for scoring.
        conn.execute("UPDATE articles SET published_at = NULL, fetched_at = ? WHERE url LIKE '%no-date'",
                     (published(5).isoformat(),))
    assert candidates(conn) == ["https://example.com/recent"]


def test_candidates_skip_sent_articles(conn):
    sent = scored(conn, "https://example.com/sent", 10)
    scored(conn, "https://example.com/new", 8)
    mark_sent(conn, [sent], sent_at=NOW)
    assert candidates(conn) == ["https://example.com/new"]


def test_candidates_carry_the_llm_results(conn):
    article_id = add(conn, "https://example.com/a", published_at=published(1), content="Text", source="rss")
    save_score(conn, article_id, score=9, reason="Very relevant.", interests=["ai-agents", "python"], scored_with="m")
    save_summary(conn, article_id, "What it brings.")
    [candidate] = fetch_digest_candidates(conn, 8, 3, now=NOW)
    assert candidate.id == article_id
    assert (candidate.score, candidate.reason, candidate.summary) == (9, "Very relevant.", "What it brings.")
    assert candidate.interests == ("ai-agents", "python")
    assert (candidate.article.url, candidate.article.source, candidate.article.content) == (
        "https://example.com/a", "rss", "Text",
    )


def test_candidates_without_summary_are_included(conn):
    scored(conn, "https://example.com/link-only", 9, summary=None)
    [candidate] = fetch_digest_candidates(conn, 8, 3, now=NOW)
    assert candidate.summary is None


@pytest.mark.parametrize(
    "corruption",
    [
        "url = 'javascript:alert(1)'",  # No longer passes Article's URL check.
        "interests = 'not json'",
        "interests = '{\"python\": 1}'",  # JSON, but not a list.
        "interests = '[1, 2]'",  # A list, but not of ids.
        "reason = NULL",
    ],
)
def test_candidates_skip_rows_that_are_no_longer_valid(conn, caplog, corruption):
    scored(conn, "https://example.com/good", 8)
    bad_id = scored(conn, "https://example.com/bad", 9)
    with conn:  # Simulate a row corrupted outside the agent. The SQL is fixed test text, not input.
        conn.execute(f"UPDATE articles SET {corruption} WHERE id = ?", (bad_id,))
    assert candidates(conn) == ["https://example.com/good"]
    assert f"Skipping stored article {bad_id}" in caplog.text


def test_candidates_without_now_use_the_current_time(conn):
    article_id = add(conn, "https://example.com/a", published_at=datetime.now(timezone.utc))
    save_score(conn, article_id, score=9, reason="x", interests=[], scored_with="m")
    assert len(fetch_digest_candidates(conn, 8, 3)) == 1


def test_best_recent_score(conn):
    assert best_recent_score(conn, 3, now=NOW) is None  # Nothing scored.
    add(conn, "https://example.com/unscored", published_at=published(1))
    assert best_recent_score(conn, 3, now=NOW) is None
    scored(conn, "https://example.com/six", 6)
    scored(conn, "https://example.com/seven", 7)
    assert best_recent_score(conn, 3, now=NOW) == 7


def test_best_recent_score_ignores_sent_and_old_articles(conn):
    scored(conn, "https://example.com/five", 5)
    mark_sent(conn, [scored(conn, "https://example.com/sent", 10)], sent_at=NOW)
    scored(conn, "https://example.com/old", 9, days_ago=10)
    assert best_recent_score(conn, 3, now=NOW) == 5


def test_mark_sent_only_marks_the_given_articles(conn):
    first = scored(conn, "https://example.com/a", 9)
    second = scored(conn, "https://example.com/b", 9)
    third = scored(conn, "https://example.com/c", 9)
    mark_sent(conn, [first, third], sent_at=NOW)
    sent = {row["id"]: row["sent_at"] for row in rows(conn)}
    assert datetime.fromisoformat(sent[first]) == NOW
    assert datetime.fromisoformat(sent[third]) == NOW
    assert sent[second] is None


def test_mark_sent_defaults_to_now_in_utc(conn):
    article_id = scored(conn, "https://example.com/a", 9)
    mark_sent(conn, [article_id])
    assert datetime.fromisoformat(rows(conn)[0]["sent_at"]).tzinfo == timezone.utc


def test_mark_sent_with_no_article_does_nothing(conn):
    scored(conn, "https://example.com/a", 9)
    mark_sent(conn, [])
    assert rows(conn)[0]["sent_at"] is None


def test_mark_sent_is_committed_immediately(tmp_path):
    db_path = tmp_path / "test.db"
    writer = connect(db_path)
    article_id = scored(writer, "https://example.com/a", 9)
    mark_sent(writer, [article_id], sent_at=NOW)
    reader = sqlite3.connect(db_path)
    assert reader.execute("SELECT sent_at FROM articles").fetchone()[0] is not None
    reader.close()
    writer.close()
