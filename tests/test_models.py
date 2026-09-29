from datetime import timezone

import pytest

from tech_radar_agent.models import (
    MAX_AUTHOR_LENGTH,
    MAX_CONTENT_LENGTH,
    MAX_TITLE_LENGTH,
    Article,
    normalize_url,
)


class TestNormalizeUrl:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("https://example.com/a", "https://example.com/a"),
            ("HTTPS://Example.COM/a", "https://example.com/a"),
            ("https://example.com/a/", "https://example.com/a"),
            ("https://example.com/a#section", "https://example.com/a"),
            ("https://example.com/a?utm_source=hn&utm_medium=social", "https://example.com/a"),
            ("https://example.com/a?fbclid=123&gclid=456&ref=twitter", "https://example.com/a"),
            ("https://example.com/a?b=2&a=1", "https://example.com/a?a=1&b=2"),
            ("https://example.com/a?id=7&utm_source=hn", "https://example.com/a?id=7"),
            ("https://www.youtube.com/watch?v=abc123", "https://www.youtube.com/watch?v=abc123"),
            ("  https://example.com/a  ", "https://example.com/a"),
        ],
    )
    def test_normalization(self, url, expected):
        assert normalize_url(url) == expected

    def test_path_case_is_kept(self):
        # Paths can be case-sensitive on the server: only the domain is lowercased.
        assert normalize_url("https://example.com/ReadMe") == "https://example.com/ReadMe"

    @pytest.mark.parametrize(
        ("first", "second"),
        [
            ("https://www.example.com/a", "https://example.com/a"),
            ("http://example.com/a", "https://example.com/a"),
        ],
    )
    def test_known_limitations_are_not_merged(self, first, second):
        # Deliberately not handled yet (see docs/decisions/0003). Update this test if that changes.
        assert normalize_url(first) != normalize_url(second)


def make_article(**overrides) -> Article:
    fields = {"source": "test", "title": "A title", "url": "https://example.com/a"}
    return Article(**(fields | overrides))


class TestArticle:
    def test_defaults(self):
        article = make_article()
        assert article.author is None
        assert article.content is None
        assert article.published_at is None
        assert article.extra == {}

    def test_fetched_at_is_set_in_utc(self):
        assert make_article().fetched_at.tzinfo == timezone.utc

    def test_extra_is_not_shared_between_articles(self):
        first, second = make_article(), make_article()
        first.extra["points"] = 10
        assert second.extra == {}

    def test_normalized_url_follows_url(self):
        article = make_article(url="https://Example.com/a/?utm_source=x")
        assert article.normalized_url == "https://example.com/a"
        article.url = "https://example.com/b"
        assert article.normalized_url == "https://example.com/b"

    def test_url_is_kept_as_given(self):
        # The original URL is the one shown in the digest.
        assert make_article(url="https://Example.com/a/?utm_source=x").url == "https://Example.com/a/?utm_source=x"


class TestArticleSecurity:
    @pytest.mark.parametrize("url", ["javascript:alert(1)", "data:text/html,x", "file:///etc/passwd", "https://"])
    def test_unsafe_url_is_rejected(self, url):
        with pytest.raises(ValueError, match="URL"):
            make_article(url=url)

    @pytest.mark.parametrize("title", ["", "   ", "​"])
    def test_empty_title_is_rejected(self, title):
        with pytest.raises(ValueError, match="title"):
            make_article(title=title)

    def test_text_fields_are_cleaned(self):
        article = make_article(title="Hello​  world", author=" bob\n", content="Hi‮ there")
        assert article.title == "Hello world"
        assert article.author == "bob"
        assert article.content == "Hi there"

    def test_text_fields_are_truncated(self):
        article = make_article(title="t" * 1000, author="a" * 1000, content="c" * 10_000)
        assert len(article.title) == MAX_TITLE_LENGTH
        assert len(article.author) == MAX_AUTHOR_LENGTH
        assert len(article.content) == MAX_CONTENT_LENGTH

    def test_blank_optional_fields_become_none(self):
        article = make_article(author="  ", content="​")
        assert article.author is None
        assert article.content is None
