"""Labels written by the code (section titles, date, activity report), in the reader's language.

The LLM writes reasons and summaries in `profile.language` by itself; the fixed labels around them come
from one JSON file per language in this folder (ADR 0025):

    load_labels(language)   -> Labels   the labels for `profile.language`, or English
    labels.text(key, **values)          one label, with its $placeholders filled in
    labels.date(day)                    "Monday 6 October", "lundi 6 octobre"

The contract lives in the code, which uses the labels: LABELS lists every label and the placeholders
it takes. Every file, English included, must match it exactly (checked by the tests, and again when a
file is loaded). en.json is the default and the file to copy: adding a language means adding one
file, which any LLM can translate from en.json; its `language_names` tell which `profile.language`
values select it.

Placeholders use string.Template ($minutes), not str.format: Template only replaces names, while
str.format can read attributes ({x.__class__}) and a translated file is text nobody here wrote.
Labels are plain text: the caller escapes them like any other text before putting them in HTML.
"""

import json
import logging
from dataclasses import dataclass
from datetime import date
from importlib import resources
from string import Template
from typing import Any

logger = logging.getLogger(__name__)

REFERENCE = "en"  # The default language, the fallback, and the file to copy to translate.

# Every label the code uses -> the placeholders it takes. Adding a label means adding it here AND in
# every file: the tests fail until all files have it.
LABELS: dict[str, frozenset[str]] = {
    "header": frozenset({"date"}),
    "article_count_one": frozenset({"count", "minutes"}),
    "article_count_other": frozenset({"count", "minutes"}),
    "to_read": frozenset(),
    "also_worth_a_look": frozenset(),
    "why": frozenset(),
    "discussion": frozenset(),
    "empty_report": frozenset({"threshold", "collected", "scored", "best"}),
    "empty_report_nothing_scored": frozenset({"collected"}),
    "date": frozenset({"weekday", "day", "month"}),
}
LIST_KEYS = {"language_names": None, "weekdays": 7, "months": 12}  # Key -> required length (None: any).


@dataclass(frozen=True)
class Labels:
    """The labels of one language, already checked against LABELS."""

    code: str  # File name without .json, e.g. "fr".
    texts: dict[str, str]  # Label key -> template text.
    weekdays: tuple[str, ...]  # Monday first, like date.weekday().
    months: tuple[str, ...]  # January first.

    def text(self, key: str, **values: object) -> str:
        """One label with its placeholders filled in. A missing value is a bug: KeyError."""
        return Template(self.texts[key]).substitute(values)

    def date(self, day: date) -> str:
        """A date written in this language, without relying on the system locale (absent in CI)."""
        return self.text(
            "date", weekday=self.weekdays[day.weekday()], day=day.day, month=self.months[day.month - 1]
        )


def load_labels(language: str) -> Labels:
    """The labels for `profile.language`, matched against each file's `language_names` (any case).

    Falls back to English when no file declares this language, or when its file is invalid: a label
    problem must never cost the day's digest. An invalid English file is a bug and raises ValueError.
    """
    reference = _read(REFERENCE)
    _check(REFERENCE, reference)  # Raises: without a valid English file there is no fallback.
    wanted = language.strip().casefold()

    for code in available_codes():
        data = reference if code == REFERENCE else _read(code)
        names = {str(name).strip().casefold() for name in data.get("language_names", [])}
        if wanted not in names | {code}:
            continue
        try:
            _check(code, data)
        except ValueError as error:
            logger.warning("Invalid translation %s.json (%s): labels in English", code, error)
            break
        return _labels(code, data)

    if wanted not in {name.casefold() for name in reference["language_names"]} | {REFERENCE}:
        logger.info("No translation for %r: labels in English", language)
    return _labels(REFERENCE, reference)


def available_codes() -> list[str]:
    """The language files shipped with the package, e.g. ["en", "fr"], sorted."""
    folder = resources.files(__package__)
    return sorted(entry.name.removesuffix(".json") for entry in folder.iterdir() if entry.name.endswith(".json"))


def _read(code: str) -> dict[str, Any]:
    data = json.loads(resources.files(__package__).joinpath(f"{code}.json").read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{code}.json must be a JSON object")
    return data


def _check(code: str, data: dict[str, Any]) -> None:
    """Raise ValueError unless `data` has exactly the keys of the contract, each label exactly its placeholders."""
    expected_keys = set(LABELS) | set(LIST_KEYS)
    if set(data) != expected_keys:
        missing, extra = sorted(expected_keys - set(data)), sorted(set(data) - expected_keys)
        raise ValueError(f"{code}.json keys differ from the contract (missing {missing}, unexpected {extra})")

    for key, length in LIST_KEYS.items():
        value = data[key]
        texts_ok = isinstance(value, list) and all(isinstance(item, str) and item.strip() for item in value)
        if not texts_ok or not value:
            raise ValueError(f"{code}.json: `{key}` must be a list of non-empty texts")
        if length is not None and len(value) != length:
            raise ValueError(f"{code}.json: `{key}` must have {length} items, got {len(value)}")

    for key, placeholders in LABELS.items():
        text = data[key]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"{code}.json: `{key}` must be a non-empty text")
        template = Template(text)
        if not template.is_valid():
            raise ValueError(f"{code}.json: `{key}` has a malformed placeholder")
        if set(template.get_identifiers()) != placeholders:
            raise ValueError(
                f"{code}.json: `{key}` placeholders {sorted(template.get_identifiers())}, "
                f"expected {sorted(placeholders)}"
            )


def _labels(code: str, data: dict[str, Any]) -> Labels:
    texts = {key: value for key, value in data.items() if key not in LIST_KEYS}
    return Labels(code=code, texts=texts, weekdays=tuple(data["weekdays"]), months=tuple(data["months"]))
