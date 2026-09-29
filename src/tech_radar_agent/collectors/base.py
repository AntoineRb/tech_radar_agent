import html
import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from tech_radar_agent.models import Article

USER_AGENT = "tech-radar-agent/0.1 (+https://github.com/AntoineRb/tech_radar_agent)"

# Protects against huge or endless responses (and compression bombs: the limit applies after decompression).
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class UnsafeResponseError(httpx.HTTPError):
    """A response refused by the security rules: not HTTPS, or too large."""


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


def http_client(transport: httpx.BaseTransport | None = None) -> httpx.Client:
    """Return an HTTP client with the settings shared by all collectors.

    `transport` replaces the network layer, e.g. with `httpx.MockTransport` in tests.
    """
    return httpx.Client(
        timeout=10,
        headers={"User-Agent": USER_AGENT},
        follow_redirects=True,
        transport=transport,
    )


def fetch(client: httpx.Client, url: str) -> bytes:
    """GET `url` over HTTPS only, reading at most MAX_RESPONSE_BYTES. Use this instead of `client.get`."""
    if not url.startswith("https://"):
        raise UnsafeResponseError(f"Refusing non-HTTPS URL: {url}")
    with client.stream("GET", url) as response:
        response.raise_for_status()
        if response.url.scheme != "https":  # A redirect may have downgraded the connection.
            raise UnsafeResponseError(f"Redirected to non-HTTPS URL: {response.url}")
        body = bytearray()
        for chunk in response.iter_bytes():
            body += chunk
            if len(body) > MAX_RESPONSE_BYTES:
                raise UnsafeResponseError(f"Response larger than {MAX_RESPONSE_BYTES} bytes: {url}")
    return bytes(body)


def fetch_json(client: httpx.Client, url: str) -> Any:
    """Like `fetch`, then decode the body as JSON."""
    return json.loads(fetch(client, url))


def html_to_text(value: str | None) -> str | None:
    """Turn an HTML snippet into plain text. Return None if nothing is left.

    Invisible characters and length are handled later by Article itself.
    """
    if not value:
        return None
    text = re.sub(r"<[^>]+>", " ", value)  # Drop tags, keep their content.
    text = " ".join(html.unescape(text).split())  # Decode entities, collapse whitespace.
    return text or None
