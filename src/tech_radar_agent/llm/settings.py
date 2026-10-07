import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# The only hosts allowed over plain http: a model served on this machine (e.g. Ollama).
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

# Covers a local model loading into memory on its first call (~20 s measured with qwen3.6).
DEFAULT_REQUEST_TIMEOUT = 30.0

# Upper bound of LLM_MIN_INTERVAL_SECONDS: a larger value is a typo (e.g. milliseconds), and would
# silently stretch a run over hours (ADR 0029).
MAX_MIN_INTERVAL = 300.0


@dataclass(frozen=True)
class LlmSettings:
    """Where the LLM is and how to call it: any server speaking the OpenAI chat completions format.

    Local (Ollama): base_url="http://localhost:11434/v1", no api_key.
    Remote API: base_url="https://...", api_key required by most providers.
    """

    base_url: str  # Without trailing slash, e.g. "http://localhost:11434/v1".
    model: str
    api_key: str | None = field(default=None, repr=False)  # repr=False: never printed in logs.
    # Sent as "reasoning_effort" in every request when set (e.g. "none" turns off a model's thinking).
    # None: the field is not sent, for servers that do not support it.
    reasoning_effort: str | None = None
    request_timeout: float = DEFAULT_REQUEST_TIMEOUT  # Seconds, for one LLM call.
    # Seconds between the starts of two LLM requests, to stay under a per-minute quota (e.g. a
    # provider's free tier). 0: no wait.
    min_interval: float = 0.0

    @property
    def is_local(self) -> bool:
        return urlsplit(self.base_url).hostname in LOCAL_HOSTS


def is_allowed_llm_url(url: str) -> bool:
    """HTTPS everywhere, plain http only towards this machine (docs/security.md)."""
    parts = urlsplit(url)
    if parts.scheme == "https":
        return bool(parts.hostname)
    return parts.scheme == "http" and parts.hostname in LOCAL_HOSTS


def load_llm_settings(environ: Mapping[str, str] = os.environ) -> LlmSettings:
    """Read the LLM_* environment variables (see .env.example)."""
    base_url = environ.get("LLM_BASE_URL", "").strip().rstrip("/")
    model = environ.get("LLM_MODEL", "").strip()
    api_key = environ.get("LLM_API_KEY", "").strip() or None
    reasoning_effort = environ.get("LLM_REASONING_EFFORT", "").strip() or None
    raw_timeout = environ.get("LLM_REQUEST_TIMEOUT", "").strip()
    raw_interval = environ.get("LLM_MIN_INTERVAL_SECONDS", "").strip()

    missing = [name for name, value in (("LLM_BASE_URL", base_url), ("LLM_MODEL", model)) if not value]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    if not is_allowed_llm_url(base_url):
        raise ValueError(f"LLM_BASE_URL must use https, or http on localhost only: {base_url!r}")

    return LlmSettings(
        base_url=base_url,
        model=model,
        api_key=api_key,
        reasoning_effort=reasoning_effort,
        request_timeout=parse_timeout(raw_timeout) if raw_timeout else DEFAULT_REQUEST_TIMEOUT,
        min_interval=parse_min_interval(raw_interval) if raw_interval else 0.0,
    )


def parse_timeout(value: str) -> float:
    """A strictly positive number of seconds, e.g. "30" or "2.5"."""
    try:
        timeout = float(value)
    except ValueError:
        raise ValueError(f"LLM_REQUEST_TIMEOUT must be a number of seconds, got {value!r}") from None
    if not 0 < timeout < float("inf"):  # Also rejects "nan" and "inf".
        raise ValueError(f"LLM_REQUEST_TIMEOUT must be a positive number of seconds, got {value!r}")
    return timeout


def parse_min_interval(value: str) -> float:
    """A number of seconds from 0 (no wait) to MAX_MIN_INTERVAL, e.g. "6" or "4.5"."""
    try:
        interval = float(value)
    except ValueError:
        raise ValueError(f"LLM_MIN_INTERVAL_SECONDS must be a number of seconds, got {value!r}") from None
    if not 0 <= interval <= MAX_MIN_INTERVAL:  # Also rejects "nan" and "inf".
        raise ValueError(
            f"LLM_MIN_INTERVAL_SECONDS must be between 0 and {MAX_MIN_INTERVAL:g} seconds, got {value!r}"
        )
    return interval
