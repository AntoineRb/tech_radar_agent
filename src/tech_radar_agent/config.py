import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path("config/interests.yaml")
DEFAULT_LANGUAGE = "English"

# From most to least important. Also the order in which interests are listed.
PRIORITIES = ("high", "medium", "low")

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
class Config:
    profile: Profile
    sources: list[dict[str, Any]]  # Raw entries, turned into collectors by build_collector().


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> Config:
    """Read the YAML config (interest profile and sources) and check it entirely."""
    with path.open(encoding="utf-8") as file:
        raw = yaml.safe_load(file)  # Never yaml.load: it can build arbitrary Python objects.

    if not isinstance(raw, dict):
        raise ValueError(f"{path}: expected a mapping at the top level")
    try:
        return Config(profile=parse_profile(raw.get("profile")), sources=parse_sources(raw.get("sources")))
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


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"`{name}` must be a non-empty text")
    return " ".join(value.split())  # Folded YAML (`>`) and stray newlines become single spaces.
