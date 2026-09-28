import html
import re
from abc import ABC, abstractmethod

import httpx

from tech_radar_agent.models import Article

USER_AGENT = "tech-radar-agent/0.1 (+https://github.com/AntoineRb/tech_radar_agent)"


class Collector(ABC):
    """A source of articles.

    Each subclass handles one kind of source and sets `type`, the identifier used in the config.
    Its constructor takes the source options from the config as keyword arguments.
    """

    type: str  # e.g. "hackernews", "rss".

    def __init__(self, name: str | None = None) -> None:
        # Stored as Article.source. Distinct names let several sources share a type (e.g. many RSS feeds).
        self.name = name or self.type

    @abstractmethod
    def collect(self) -> list[Article]:
        """Fetch the source and return its articles.

        Raise if the whole source is unreachable; skip individual items that fail.
        """

    def __repr__(self) -> str:
        return f"{type(self).__name__}(name={self.name!r})"


def http_client() -> httpx.Client:
    """Return an HTTP client with the settings shared by all collectors."""
    return httpx.Client(
        timeout=10,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
    )


def html_to_text(value: str | None) -> str | None:
    """Turn an HTML snippet into plain text for the LLM. Return None if nothing is left."""
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)  # Drop tags, keep their content.
    text = " ".join(html.unescape(text).split())  # Decode entities, collapse whitespace.
    return text or None
