from datetime import datetime, timezone

import httpx
import pytest

from tech_radar_agent.collectors.hackernews import API_URL, HackerNewsCollector

TOP_URL = f"{API_URL}/topstories.json"


def item_url(item_id: int) -> str:
    return f"{API_URL}/item/{item_id}.json"


def story(item_id: int, **fields) -> dict:
    return {
        "id": item_id,
        "type": "story",
        "title": f"Story {item_id}",
        "url": f"https://example.com/{item_id}",
        "by": "alice",
        "time": 1_790_000_000,
        "score": 100,
        "descendants": 12,
    } | fields


def serve(fake_http, *items: dict, feed_url: str = TOP_URL) -> None:
    fake_http.routes[feed_url] = [item["id"] for item in items]
    for item in items:
        fake_http.routes[item_url(item["id"])] = item


class TestMapping:
    def test_link_story(self, fake_http):
        serve(fake_http, story(1))
        [article] = HackerNewsCollector().collect()

        assert article.source == "hackernews"
        assert article.title == "Story 1"
        assert article.url == "https://example.com/1"
        assert article.author == "alice"
        assert article.content is None
        assert article.published_at == datetime.fromtimestamp(1_790_000_000, tz=timezone.utc)
        assert article.extra == {
            "hn_id": 1,
            "points": 100,
            "comments": 12,
            "discussion_url": "https://news.ycombinator.com/item?id=1",
        }

    def test_ask_hn_links_to_the_discussion_and_keeps_its_text(self, fake_http):
        serve(fake_http, story(2, url=None, text="<p>What do you use for <i>X</i>?</p>"))
        [article] = HackerNewsCollector().collect()
        assert article.url == "https://news.ycombinator.com/item?id=2"
        assert article.content == "What do you use for X ?"

    def test_missing_counters_default_to_zero(self, fake_http):
        item = story(3)
        del item["score"], item["descendants"], item["time"]
        serve(fake_http, item)
        [article] = HackerNewsCollector().collect()
        assert article.extra["points"] == 0
        assert article.extra["comments"] == 0
        assert article.published_at is None

    def test_custom_name_is_the_source(self, fake_http):
        serve(fake_http, story(1))
        [article] = HackerNewsCollector(name="hn-top").collect()
        assert article.source == "hn-top"


class TestFiltering:
    @pytest.mark.parametrize(
        "unwanted",
        [
            {"deleted": True},
            {"dead": True},
            {"type": "comment"},
            {"type": "job"},
            {"type": "poll"},
            {"title": ""},
        ],
    )
    def test_unwanted_items_are_skipped(self, fake_http, unwanted):
        serve(fake_http, story(1), story(2, **unwanted))
        assert [a.title for a in HackerNewsCollector().collect()] == ["Story 1"]

    def test_unknown_item_is_skipped(self, fake_http):
        serve(fake_http, story(1))
        fake_http.routes[TOP_URL] = [1, 999]
        fake_http.routes[item_url(999)] = None  # The API returns null for unknown ids.
        assert len(HackerNewsCollector().collect()) == 1

    def test_min_points(self, fake_http):
        serve(fake_http, story(1, score=50), story(2, score=49))
        assert [a.title for a in HackerNewsCollector(min_points=50).collect()] == ["Story 1"]

    def test_limit_is_applied_before_fetching_items(self, fake_http):
        serve(fake_http, story(1), story(2), story(3))
        assert len(HackerNewsCollector(limit=2).collect()) == 2
        assert item_url(3) not in fake_http.requested_urls()

    def test_unsafe_url_is_skipped(self, fake_http):
        serve(fake_http, story(1), story(2, url="javascript:alert(1)"))
        assert [a.title for a in HackerNewsCollector().collect()] == ["Story 1"]


class TestErrors:
    @pytest.mark.parametrize("failure", [500, httpx.ConnectError("boom"), "not json"])
    def test_failing_item_is_skipped(self, fake_http, failure):
        serve(fake_http, story(1), story(2))
        fake_http.routes[item_url(2)] = failure
        assert [a.title for a in HackerNewsCollector().collect()] == ["Story 1"]

    def test_unreachable_story_list_raises(self, fake_http):
        fake_http.routes[TOP_URL] = 503
        with pytest.raises(httpx.HTTPStatusError):
            HackerNewsCollector().collect()


class TestOptions:
    @pytest.mark.parametrize(
        ("feed", "endpoint"),
        [("top", "topstories"), ("new", "newstories"), ("best", "beststories"), ("ask", "askstories"), ("show", "showstories")],
    )
    def test_feed_selects_the_endpoint(self, fake_http, feed, endpoint):
        serve(fake_http, story(1), feed_url=f"{API_URL}/{endpoint}.json")
        assert len(HackerNewsCollector(feed=feed).collect()) == 1

    def test_unknown_feed_is_rejected(self):
        with pytest.raises(ValueError, match="Unknown Hacker News feed"):
            HackerNewsCollector(feed="trending")
