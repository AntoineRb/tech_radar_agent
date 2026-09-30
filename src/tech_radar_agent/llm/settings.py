import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from urllib.parse import urlsplit

# The only hosts allowed over plain http: a model served on this machine (e.g. Ollama).
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


@dataclass(frozen=True)
class LlmSettings:
    """Where the LLM is: any server speaking the OpenAI chat completions format.

    Local (Ollama): base_url="http://localhost:11434/v1", no api_key.
    Remote API: base_url="https://...", api_key required by most providers.
    """

    base_url: str  # Without trailing slash, e.g. "http://localhost:11434/v1".
    model: str
    api_key: str | None = field(default=None, repr=False)  # repr=False: never printed in logs.

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
    """Read LLM_BASE_URL, LLM_MODEL and the optional LLM_API_KEY from the environment."""
    base_url = environ.get("LLM_BASE_URL", "").strip().rstrip("/")
    model = environ.get("LLM_MODEL", "").strip()
    api_key = environ.get("LLM_API_KEY", "").strip() or None

    missing = [name for name, value in (("LLM_BASE_URL", base_url), ("LLM_MODEL", model)) if not value]
    if missing:
        raise ValueError(f"Missing environment variables: {', '.join(missing)} (see .env.example)")
    if not is_allowed_llm_url(base_url):
        raise ValueError(f"LLM_BASE_URL must use https, or http on localhost only: {base_url!r}")

    return LlmSettings(base_url=base_url, model=model, api_key=api_key)
