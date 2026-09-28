import logging
import time
from datetime import datetime, timezone
from typing import Any

import feedparser

from tech_radar_agent.collectors.base import Collector, fetch, html_to_text, http_client
from tech_radar_agent.models import Article

logger = logging.getLogger(__name__)


class RssCollector(Collector):
    """Entries of one RSS or Atom feed, parsed with feedparser."""

    type = "rss"

    def __init__(self, url: str, name: str | None = None, limit: int = 30) -> None:
        super().__init__(name)
        self.url = url
        self.limit = limit  # Feeds are newest first: keep the most recent entries.

    def collect(self) -> list[Article]:
        # Download through fetch() (HTTPS, size limit), then let feedparser parse the bytes offline.
        with http_client() as client:
            feed = feedparser.parse(fetch(client, self.url))

        # "bozo" flags a malformed feed. feedparser often recovers, so only fail if nothing came out.
        if feed.bozo and not feed.entries:
            raise ValueError(f"Unreadable feed {self.url}: {feed.bozo_exception}")

        feed_title = feed.feed.get("title")
        articles = []
        for entry in feed.entries[: self.limit]:
            try:
                articles.append(self._to_article(entry, feed_title))
            except (KeyError, ValueError) as error:  # No link or title, or rejected by Article's checks.
                logger.warning("%s: skipping entry %r (%s)", self.name, entry.get("title"), error)

        logger.info("%s: %d articles from %d entries", self.name, len(articles), len(feed.entries))
        return articles

    def _to_article(self, entry: Any, feed_title: str | None) -> Article:
        return Article(
            source=self.name,
            title=html_to_text(entry.get("title")) or "",
            url=entry["link"],
            author=entry.get("author"),
            content=html_to_text(self._content(entry)),
            published_at=self._date(entry),
            extra={
                "feed_title": feed_title,
                "tags": [tag["term"] for tag in entry.get("tags", []) if tag.get("term")],
            },
        )

    @staticmethod
    def _content(entry: Any) -> str | None:
        # Atom <content> holds the full text; <summary>/<description> is often a shorter excerpt.
        if entry.get("content"):
            return entry.content[0].get("value")
        return entry.get("summary")

    @staticmethod
    def _date(entry: Any) -> datetime | None:
        # feedparser gives dates as UTC time.struct_time, whatever the offset in the feed.
        parsed: time.struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
        if parsed is None:
            return None
        return datetime(*parsed[:6], tzinfo=timezone.utc)
