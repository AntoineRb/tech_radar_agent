from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query parameters that only track where a click came from, never which page it is.
TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}

def normalize_url(url: str) -> str:
    """Return a canonical form of `url`, used as a deduplication key."""
    parts = urlsplit(url.strip())

    # Keep only meaningful query parameters, sorted so their order doesn't matter.
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query)
        if not key.startswith("utm_") and key not in TRACKING_PARAMS
    ]

    return urlunsplit((
        parts.scheme.lower(),
        parts.netloc.lower(),
        parts.path.rstrip("/"),
        urlencode(sorted(query)),
        "",  # Drop the #fragment: it points inside the page, not to another page.
    ))

@dataclass
class Article:
    """A piece of content collected from any source, before any LLM processing."""

    # Required fields first: every collector must provide them.
    source: str  # Name of the collector instance, e.g. "hackernews", "hn-best", "rss-lobsters".
    title: str
    url: str

    # Optional fields: not every source provides them.
    author: str | None = None
    content: str | None = None  # Text excerpt for the LLM; None for link-only posts.
    published_at: datetime | None = None

    # Set automatically when the article is created.
    fetched_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Source-specific data (HN points, GitHub stars...), kept out of the common schema.
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def normalized_url(self) -> str:
        """Deduplication key: the same page always gives the same value."""
        return normalize_url(self.url)