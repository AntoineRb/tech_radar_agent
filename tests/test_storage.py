import json
from datetime import datetime, timezone

import pytest

from tech_radar_agent.models import Article
from tech_radar_agent.storage import connect, save_articles


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


def test_extra_values_that_are_not_json_are_stored_as_text(conn):
    when = datetime(2026, 9, 1, tzinfo=timezone.utc)
    save_articles(conn, [make_article(extra={"seen": when})])
    assert json.loads(rows(conn)[0]["extra"]) == {"seen": str(when)}
