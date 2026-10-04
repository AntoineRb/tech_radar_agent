import os
from collections.abc import Mapping
from dataclasses import dataclass

from tech_radar_agent.agent.scoring import MAX_SCORE, MIN_SCORE

DEFAULT_MAX_ARTICLE_AGE_DAYS = 3  # Absorbs a missed daily run without scoring month-old articles.
DEFAULT_MAX_ARTICLES_PER_RUN = 100  # Safety cap on time and cost; a normal day has fewer new articles.
DEFAULT_SUMMARY_THRESHOLD = 8  # Measured on 25 articles: about a third pass. To tune per model.


@dataclass(frozen=True)
class AgentSettings:
    """How much the agent processes per run. Set by environment variables, see .env.example."""

    max_article_age_days: int = DEFAULT_MAX_ARTICLE_AGE_DAYS  # Older unscored articles are never scored.
    max_articles_per_run: int = DEFAULT_MAX_ARTICLES_PER_RUN  # Newest first.
    summary_threshold: int = DEFAULT_SUMMARY_THRESHOLD  # Articles scored at least this get a summary.


def load_agent_settings(environ: Mapping[str, str] = os.environ) -> AgentSettings:
    """Read the AGENT_* environment variables. Each one is optional and falls back to its default."""
    return AgentSettings(
        max_article_age_days=_int_setting(environ, "AGENT_MAX_ARTICLE_AGE_DAYS", DEFAULT_MAX_ARTICLE_AGE_DAYS, 1, 365),
        max_articles_per_run=_int_setting(environ, "AGENT_MAX_ARTICLES_PER_RUN", DEFAULT_MAX_ARTICLES_PER_RUN, 1, 10_000),
        summary_threshold=_int_setting(environ, "AGENT_SUMMARY_THRESHOLD", DEFAULT_SUMMARY_THRESHOLD, MIN_SCORE, MAX_SCORE),
    )


def _int_setting(environ: Mapping[str, str], name: str, default: int, minimum: int, maximum: int) -> int:
    """An integer from `minimum` to `maximum`, or `default` when the variable is unset or empty."""
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a whole number, got {raw!r}") from None
    if not minimum <= value <= maximum:
        raise ValueError(f"{name} must be between {minimum} and {maximum}, got {value}")
    return value
