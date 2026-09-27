from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class Article:
    """A piece of content collected from any source, before any LLM processing."""

    # Required fields first: every collector must provide them.
    source: str  # Collector name, e.g. "hackernews", "github", "rss", "arxiv".
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
