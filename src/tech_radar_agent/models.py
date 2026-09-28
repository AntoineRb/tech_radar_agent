from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tech_radar_agent.sanitize import clean_text, is_safe_url

# Query parameters that only track where a click came from, never which page it is.
TRACKING_PARAMS = {"fbclid", "gclid", "ref", "ref_src", "mc_cid", "mc_eid"}

# Maximum lengths of collected text. Content is cut to bound the LLM token cost.
MAX_TITLE_LENGTH = 300
MAX_AUTHOR_LENGTH = 100
MAX_CONTENT_LENGTH = 3000

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

    def __post_init__(self) -> None:
        # Collected data is untrusted (docs/security.md): enforce the rules here so no collector can skip them.
        if not is_safe_url(self.url):
            raise ValueError(f"Unsafe or invalid URL: {self.url!r}")
        title = clean_text(self.title, MAX_TITLE_LENGTH)
        if title is None:
            raise ValueError("Article title is empty")
        self.title = title
        self.author = clean_text(self.author, MAX_AUTHOR_LENGTH)
        self.content = clean_text(self.content, MAX_CONTENT_LENGTH)

    @property
    def normalized_url(self) -> str:
        """Deduplication key: the same page always gives the same value."""
        return normalize_url(self.url)