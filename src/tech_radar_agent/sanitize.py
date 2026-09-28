"""Defenses for untrusted collected data (see docs/security.md)."""

import unicodedata
from urllib.parse import urlsplit

# Format (zero-width, bidi overrides, invisible "tag" characters), private-use and surrogate
# characters can hide text from a human reader while an LLM still reads it.
HIDDEN_CATEGORIES = {"Cf", "Co", "Cs"}

SAFE_URL_SCHEMES = {"http", "https"}


def clean_text(value: str | None, max_length: int) -> str | None:
    """Return `value` as plain visible text, on one line, cut to `max_length` characters.

    Return None if nothing is left.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", value)  # Fold look-alike forms (e.g. fullwidth letters).
    text = "".join(
        " " if unicodedata.category(char) == "Cc" else char  # Control characters become spaces.
        for char in text
        if unicodedata.category(char) not in HIDDEN_CATEGORIES
    )
    text = " ".join(text.split())[:max_length].rstrip()
    return text or None


def is_safe_url(url: str) -> bool:
    """Accept only web links with a host: no javascript:, data:, file:..."""
    parts = urlsplit(url.strip())
    return parts.scheme in SAFE_URL_SCHEMES and bool(parts.netloc)
