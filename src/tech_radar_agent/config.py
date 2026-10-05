import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/interests.yaml")
DEFAULT_LANGUAGE = "English"

# From most to least important. Also the order in which interests are listed.
PRIORITIES = ("high", "medium", "low")

# Digest: how long the reader wants to spend on it, in whole minutes.
DEFAULT_READING_TIME_MINUTES = 5  # "The time of a coffee."
MIN_READING_TIME_MINUTES = 1
MAX_READING_TIME_MINUTES = 30  # Beyond that it is no longer a digest; also catches a typo like 50 for 5.
DIGEST_KEYS = frozenset({"reading_time_minutes", "send_empty_report"})

# Interest ids are what the LLM returns: short, stable, easy to copy exactly ("ai-agents", "python").
INTEREST_ID = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


@dataclass(frozen=True)
class Interest:
    id: str  # Stable key returned by the LLM and stored in the database. Never rename it lightly.
    description: str  # What the LLM reads to understand the topic. Free to reword.
    priority: str  # One of PRIORITIES.


@dataclass(frozen=True)
class Profile:
    """Who the digest is for: what the LLM reads to score and summarize articles."""

    about: str
    language: str  # Language of the text shown to the user (summaries), as a plain name: "French".
    interests: tuple[Interest, ...]  # Sorted by priority, then in file order.
    not_interested: tuple[str, ...]

    @property
    def interest_ids(self) -> frozenset[str]:
        """Every valid value for the `interests` field of a scoring answer."""
        return frozenset(interest.id for interest in self.interests)


@dataclass(frozen=True)
class DigestSettings:
    """What the reader wants from the digest. Preferences, so they live in the config file (ADR 0011)."""

    # Time to read the digest and decide what to open, not to read the articles themselves.
    reading_time_minutes: int = DEFAULT_READING_TIME_MINUTES
    # On a day with no candidate, send a one-line activity report instead of nothing: silence would
    # not tell a quiet day from a broken run.
    send_empty_report: bool = True


@dataclass(frozen=True)
class Config:
    profile: Profile
    sources: list[dict[str, Any]]  # Raw entries, turned into collectors by build_collector().
    digest: DigestSettings = DigestSettings()  # The `digest` section is optional.


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the YAML config (interest profile, sources, digest) and check it entirely."""
    with path.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file)  # Never yaml.load: it can build arbitrary Python objects.

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    try:
        return Config(
            profile=parse_profile(raw.get("profile")),
            sources=parse_sources(raw.get("sources")),
            digest=parse_digest(raw.get("digest")),
        )
    except ValueError as error:
        raise ValueError(f"{path}: {error}") from None


def parse_sources(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not raw:
        raise ValueError("`sources` must be a non-empty list")
    if not all(isinstance(source, dict) for source in raw):
        raise ValueError("every source must be a mapping with at least a `type`")
    return raw


def parse_profile(raw: Any) -> Profile:
    if not isinstance(raw, dict):
        raise ValueError("`profile` must be a mapping")

    about = _required_text(raw.get("about"), "profile.about")
    language = DEFAULT_LANGUAGE if raw.get("language") is None else _required_text(raw["language"], "profile.language")

    not_interested = raw.get("not_interested") or []
    if not isinstance(not_interested, list):
        raise ValueError("`profile.not_interested` must be a list")

    return Profile(
        about=about,
        language=language,
        interests=_parse_interests(raw.get("interests")),
        not_interested=tuple(_required_text(item, "profile.not_interested[]") for item in not_interested),
    )


def _parse_interests(raw: Any) -> tuple[Interest, ...]:
    if not isinstance(raw, dict):
        raise ValueError("`profile.interests` must map priorities (high, medium, low) to interests")
    unknown = set(raw) - set(PRIORITIES)
    if unknown:
        raise ValueError(f"unknown priorities in `profile.interests`: {sorted(unknown)}, expected {list(PRIORITIES)}")

    interests: list[Interest] = []
    for priority in PRIORITIES:
        group = raw.get(priority) or {}
        if not isinstance(group, dict):
            raise ValueError(
                f"`profile.interests.{priority}` must map ids to descriptions, e.g. `python: Python (language, tooling)`"
            )
        for interest_id, description in group.items():
            if not isinstance(interest_id, str) or not INTEREST_ID.fullmatch(interest_id):
                raise ValueError(f"invalid interest id {interest_id!r}: use lowercase letters, digits and dashes")
            if any(interest.id == interest_id for interest in interests):
                raise ValueError(f"interest id {interest_id!r} is used twice")
            interests.append(Interest(interest_id, _required_text(description, f"interest {interest_id!r}"), priority))

    if not interests:
        raise ValueError("`profile.interests` must contain at least one interest")
    return tuple(interests)


def parse_digest(raw: Any) -> DigestSettings:
    """The optional `digest` section. A missing section or key keeps its default."""
    if raw is None:
        return DigestSettings()
    if not isinstance(raw, dict):
        raise ValueError("`digest` must be a mapping")
    unknown = set(raw) - DIGEST_KEYS
    if unknown:  # A misspelled key would otherwise be ignored without a word.
        raise ValueError(f"unknown keys in `digest`: {sorted(map(str, unknown))}, expected {sorted(DIGEST_KEYS)}")

    minutes = raw.get("reading_time_minutes", DEFAULT_READING_TIME_MINUTES)
    # bool is a subclass of int in Python: `true` must not be read as 1 minute.
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        raise ValueError(f"`digest.reading_time_minutes` must be a whole number of minutes, got {minutes!r}")
    if not MIN_READING_TIME_MINUTES <= minutes <= MAX_READING_TIME_MINUTES:
        raise ValueError(
            f"`digest.reading_time_minutes` must be between {MIN_READING_TIME_MINUTES} and "
            f"{MAX_READING_TIME_MINUTES}, got {minutes}"
        )

    send_empty_report = raw.get("send_empty_report", True)
    if not isinstance(send_empty_report, bool):
        raise ValueError(f"`digest.send_empty_report` must be true or false, got {send_empty_report!r}")

    return DigestSettings(reading_time_minutes=minutes, send_empty_report=send_empty_report)


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty text")
    return " ".join(value.split())  # Folded YAML (`>`) and stray newlines become single spaces.
