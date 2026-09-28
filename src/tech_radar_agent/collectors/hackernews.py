import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any

import httpx

from tech_radar_agent.collectors.base import Collector, fetch_json, html_to_text, http_client
from tech_radar_agent.models import Article

logger = logging.getLogger(__name__)

API_URL = "https://hacker-news.firebaseio.com/v0"
ITEM_PAGE_URL = "https://news.ycombinator.com/item?id={}"

# Config value -> API endpoint listing story ids.
FEEDS = {
    "top": "topstories",
    "new": "newstories",
    "best": "beststories",
    "ask": "askstories",
    "show": "showstories",
}


class HackerNewsCollector(Collector):
    """Stories from the official Hacker News API (https://github.com/HackerNews/API)."""

    type = "hackernews"

    def __init__(
        self,
        name: str | None = None,
        feed: str = "top",
        limit: int = 30,
        min_points: int = 0,
        max_workers: int = 10,
    ) -> None:
        super().__init__(name)
        if feed not in FEEDS:
            raise ValueError(f"Unknown Hacker News feed {feed!r}, expected one of {sorted(FEEDS)}")
        self.feed = feed
        self.limit = limit  # Number of stories fetched, before the min_points filter.
        self.min_points = min_points
        self.max_workers = max_workers  # The API needs one request per story: fetch them in parallel.

    def collect(self) -> list[Article]:
        with http_client() as client:
            story_ids = fetch_json(client, f"{API_URL}/{FEEDS[self.feed]}.json")[: self.limit]

            with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                items = list(pool.map(lambda story_id: self._fetch_item(client, story_id), story_ids))

        articles = []
        for item in items:
            if not self._is_wanted(item):
                continue
            try:
                articles.append(self._to_article(item))
            except ValueError as error:  # Rejected by Article's security checks.
                logger.warning("%s: skipping item %s (%s)", self.name, item["id"], error)

        logger.info("%s: %d articles from %d stories", self.name, len(articles), len(story_ids))
        return articles

    def _fetch_item(self, client: httpx.Client, item_id: int) -> dict[str, Any] | None:
        try:
            return fetch_json(client, f"{API_URL}/item/{item_id}.json")  # null for unknown ids.
        except (httpx.HTTPError, ValueError) as error:  # ValueError: invalid JSON.
            logger.warning("%s: skipping item %s (%s)", self.name, item_id, error)
            return None

    def _is_wanted(self, item: dict[str, Any] | None) -> bool:
        return (
            item is not None
            and item.get("type") == "story"
            and not item.get("deleted")
            and not item.get("dead")
            and bool(item.get("title"))
            and item.get("score", 0) >= self.min_points
        )

    def _to_article(self, item: dict[str, Any]) -> Article:
        discussion_url = ITEM_PAGE_URL.format(item["id"])
        return Article(
            source=self.name,
            title=item["title"],
            url=item.get("url") or discussion_url,  # "Ask HN" posts have no external link.
            author=item.get("by"),
            content=html_to_text(item.get("text")),
            published_at=datetime.fromtimestamp(item["time"], tz=timezone.utc) if "time" in item else None,
            extra={
                "hn_id": item["id"],
                "points": item.get("score", 0),
                "comments": item.get("descendants", 0),
                "discussion_url": discussion_url,
            },
        )
