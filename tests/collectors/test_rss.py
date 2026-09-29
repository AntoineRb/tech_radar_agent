from datetime import datetime, timezone

import httpx
import pytest

from tech_radar_agent.collectors.base import UnsafeResponseError
from tech_radar_agent.collectors.rss import RssCollector

FEED_URL = "https://example.com/feed.xml"

RSS_FEED = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel>
  <title>Example Blog</title>
  <item>
    <title>First post</title>
    <link>https://example.com/first</link>
    <author>alice@example.com (Alice)</author>
    <description>&lt;p&gt;Hello &lt;b&gt;world&lt;/b&gt;&lt;/p&gt;</description>
    <pubDate>Tue, 01 Sep 2026 12:30:00 +0200</pubDate>
    <category>python</category>
    <category>ai</category>
  </item>
  <item>
    <title>Second post</title>
    <link>https://example.com/second</link>
  </item>
  <item>
    <title>Third post</title>
    <link>https://example.com/third</link>
  </item>
</channel></rss>"""

ATOM_FEED = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Example Atom</title>
  <entry>
    <title type="html">Atom &amp;lt;entry&amp;gt;</title>
    <link href="https://example.com/atom-entry"/>
    <author><name>Bob</name></author>
    <summary>Short excerpt</summary>
    <content type="html">&lt;p&gt;The full text&lt;/p&gt;</content>
    <updated>2026-09-02T08:00:00Z</updated>
  </entry>
</feed>"""

# Everything a hostile feed could try at once.
EVIL_FEED = """<?xml version="1.0"?>
<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<rss version="2.0"><channel><title>Evil</title>
  <item>
    <title>Script​ in‮ body</title>
    <link>https://example.com/ok</link>
    <description>&lt;p&gt;Hi&lt;/p&gt;&lt;script&gt;steal()&lt;/script&gt;&lt;img src=x onerror="steal()"&gt;</description>
  </item>
  <item><title>Script link</title><link>javascript:alert(1)</link></item>
  <item><title>Data link</title><link>data:text/html,hello</link></item>
  <item><title>No link</title></item>
  <item><link>https://example.com/no-title</link></item>
</channel></rss>"""

# XML external entity (XXE): the parser must never read the local file.
# feedparser's strict parser drops the entity; on a line break after the XML declaration it falls
# back to its lenient parser, which leaves it as plain text. Both paths are tested.
XXE_DOCTYPE = '<?xml version="1.0"?>{sep}<!DOCTYPE rss [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>'
XXE_BODY = (
    '<rss version="2.0"><channel><title>t</title>'
    "<item><title>XXE &xxe;</title><link>https://example.com/xxe</link></item>"
    "</channel></rss>"
)


def collect(fake_http, feed: str, **options):
    fake_http.routes[FEED_URL] = feed
    return RssCollector(url=FEED_URL, **options).collect()


class TestRss2:
    def test_mapping(self, fake_http):
        first = collect(fake_http, RSS_FEED)[0]
        assert first.source == "rss"
        assert first.title == "First post"
        assert first.url == "https://example.com/first"
        assert first.author == "alice@example.com (Alice)"
        assert first.content == "Hello world"
        assert first.published_at == datetime(2026, 9, 1, 10, 30, tzinfo=timezone.utc)  # Converted to UTC.
        assert first.extra == {"feed_title": "Example Blog", "tags": ["python", "ai"]}

    def test_optional_fields_can_be_missing(self, fake_http):
        second = collect(fake_http, RSS_FEED)[1]
        assert second.author is None
        assert second.content is None
        assert second.published_at is None
        assert second.extra["tags"] == []

    def test_limit_keeps_the_first_entries(self, fake_http):
        articles = collect(fake_http, RSS_FEED, limit=2)
        assert [a.title for a in articles] == ["First post", "Second post"]

    def test_name_is_the_source(self, fake_http):
        assert collect(fake_http, RSS_FEED, name="example-blog")[0].source == "example-blog"


class TestAtom:
    def test_mapping(self, fake_http):
        [entry] = collect(fake_http, ATOM_FEED)
        assert entry.title == "Atom <entry>"
        assert entry.url == "https://example.com/atom-entry"
        assert entry.author == "Bob"
        assert entry.content == "The full text"  # Full content is preferred over the summary.
        assert entry.published_at == datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)  # Falls back to <updated>.


class TestSecurity:
    @pytest.fixture
    def articles(self, fake_http):
        return {a.title: a for a in collect(fake_http, EVIL_FEED)}

    def test_only_safe_entries_are_kept(self, articles):
        assert list(articles) == ["Script in body"]

    def test_scripts_and_hidden_characters_are_removed(self, articles):
        assert articles["Script in body"].content == "Hi"

    @pytest.mark.parametrize("sep", ["", "\n"], ids=["strict-parser", "lenient-parser"])
    def test_external_entities_are_not_resolved(self, fake_http, sep):
        [article] = collect(fake_http, XXE_DOCTYPE.format(sep=sep) + sep + XXE_BODY)
        assert article.title in ("XXE", "XXE &xxe;")
        assert "root:" not in article.title

    def test_feed_over_http_is_refused(self, fake_http):
        fake_http.routes["http://example.com/feed.xml"] = RSS_FEED
        with pytest.raises(UnsafeResponseError):
            RssCollector(url="http://example.com/feed.xml").collect()


class TestErrors:
    @pytest.mark.parametrize(
        "document",
        [
            "<html><body>Not a feed</body></html>",  # Well-formed: not "bozo", but not a feed either.
            "<html><body><p>Broken</body>",  # Malformed.
            "",
        ],
    )
    def test_not_a_feed_raises(self, fake_http, document):
        with pytest.raises(ValueError, match="Unreadable feed"):
            collect(fake_http, document)

    def test_empty_feed_is_not_an_error(self, fake_http):
        empty = '<?xml version="1.0"?><rss version="2.0"><channel><title>Quiet</title></channel></rss>'
        assert collect(fake_http, empty) == []

    def test_slightly_broken_feed_is_accepted(self, fake_http):
        # Unescaped "&": feedparser flags the feed as malformed ("bozo") but still reads the entries.
        broken = RSS_FEED.replace("<title>Second post</title>", "<title>Fish & chips</title>")
        assert len(collect(fake_http, broken)) == 3

    def test_unreachable_feed_raises(self, fake_http):
        fake_http.routes[FEED_URL] = httpx.ConnectError("boom")
        with pytest.raises(httpx.ConnectError):
            RssCollector(url=FEED_URL).collect()
