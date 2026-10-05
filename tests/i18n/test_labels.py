"""Tests for the i18n labels: the contract between language files, language lookup, fallback, safety.

The contract tests run on every file shipped in src/tech_radar_agent/i18n/: a new or edited translation
that misses a key or renames a placeholder fails here, in CI, not in tomorrow's digest.
"""

import copy
import json
from datetime import date
from importlib import resources
from string import Template

import pytest

from tech_radar_agent import i18n
from tech_radar_agent.i18n import LABELS, LIST_KEYS, available_codes, load_labels

CODES = available_codes()


def raw(code: str) -> dict:
    return json.loads(resources.files(i18n).joinpath(f"{code}.json").read_text(encoding="utf-8"))


TEXT_KEYS = sorted(LABELS)


# --- The files shipped with the package ---


def test_english_and_french_are_shipped():
    assert {"en", "fr"} <= set(CODES)


@pytest.mark.parametrize("code", CODES)
def test_every_file_has_exactly_the_contract_keys(code):
    assert set(raw(code)) == set(LABELS) | set(LIST_KEYS)


@pytest.mark.parametrize("code", CODES)
@pytest.mark.parametrize("key", TEXT_KEYS)
def test_every_label_has_exactly_the_contract_placeholders(code, key):
    template = Template(raw(code)[key])
    assert template.is_valid()
    assert set(template.get_identifiers()) == LABELS[key]


@pytest.mark.parametrize("code", CODES)
def test_every_file_has_seven_weekdays_and_twelve_months(code):
    data = raw(code)
    assert len(data["weekdays"]) == 7 and len(data["months"]) == 12
    assert len(set(data["weekdays"])) == 7 and len(set(data["months"])) == 12  # No copy-paste slip.


@pytest.mark.parametrize("code", CODES)
def test_labels_contain_no_markup(code):
    # Labels are escaped anyway when put in HTML; a "<" in a translation would still be a mistake.
    data = raw(code)
    texts = [data[key] for key in TEXT_KEYS] + data["weekdays"] + data["months"] + data["language_names"]
    assert not [text for text in texts if "<" in text or ">" in text]


def test_language_names_select_a_single_file():
    owners: dict[str, str] = {}
    for code in CODES:
        for name in raw(code)["language_names"]:
            assert name.casefold() not in owners, f"{name!r} is declared by {owners.get(name.casefold())} and {code}"
            owners[name.casefold()] = code


@pytest.mark.parametrize("code", CODES)
def test_every_shipped_file_loads(code):
    name = raw(code)["language_names"][0]
    assert load_labels(name).code == code


# --- Language lookup ---


@pytest.mark.parametrize("language", ["French", "french", "FRENCH", "  Français ", "Francais", "fr"])
def test_language_is_matched_whatever_the_case(language):
    assert load_labels(language).code == "fr"


def test_english_is_found_without_any_log(caplog):
    with caplog.at_level("INFO"):
        assert load_labels("English").code == "en"
    assert caplog.text == ""


@pytest.mark.parametrize("language", ["German", "Klingon", "", "French (Canada)"])
def test_unknown_language_falls_back_to_english(caplog, language):
    with caplog.at_level("INFO"):
        labels = load_labels(language)
    assert labels.code == "en"
    assert "labels in English" in caplog.text


# --- An invalid translation ---


@pytest.fixture
def shipped(monkeypatch):
    """Replace the shipped files with editable copies: {"en": {...}, "fr": {...}}."""
    files = {code: copy.deepcopy(raw(code)) for code in CODES}
    monkeypatch.setattr(i18n, "available_codes", lambda: sorted(files))
    monkeypatch.setattr(i18n, "_read", lambda code: files[code])
    return files


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(lambda fr: fr.pop("why"), id="missing-key"),
        pytest.param(lambda fr: fr.update(extra="Extra"), id="unexpected-key"),
        pytest.param(
            lambda fr: fr.update(article_count_other="$count articles · $minuts min"), id="misspelled-placeholder"
        ),
        pytest.param(lambda fr: fr.update(article_count_other="$count articles"), id="missing-placeholder"),
        pytest.param(lambda fr: fr.update(header="Tech Radar $"), id="malformed-placeholder"),
        pytest.param(lambda fr: fr.update(why=""), id="empty-label"),
        pytest.param(lambda fr: fr.update(why=["Pourquoi"]), id="label-not-text"),
        pytest.param(lambda fr: fr["weekdays"].pop(), id="six-weekdays"),
        pytest.param(lambda fr: fr.update(months="janvier"), id="months-not-a-list"),
    ],
)
def test_invalid_translation_falls_back_to_english_with_a_warning(shipped, caplog, break_it):
    break_it(shipped["fr"])
    with caplog.at_level("WARNING"):
        labels = load_labels("French")
    assert labels.code == "en"
    assert "Invalid translation fr.json" in caplog.text


@pytest.mark.parametrize(
    "break_it",
    [
        pytest.param(lambda en: en.pop("why"), id="missing-key"),
        pytest.param(lambda en: en.update(header="Tech Radar"), id="missing-placeholder"),
    ],
)
def test_invalid_english_file_is_a_bug(shipped, break_it):
    # English is the fallback: if it is broken there is nothing to fall back to. Checked against the
    # contract in the code, so a key missing from en.json is caught too (not only from translations).
    break_it(shipped["en"])
    with pytest.raises(ValueError, match="en.json"):
        load_labels("English")


# --- Using the labels ---


def test_text_fills_in_placeholders():
    labels = load_labels("English")
    assert labels.text("article_count_other", count=12, minutes=3) == "12 articles · about 3 min to scan"
    assert load_labels("French").text("to_read") == "À LIRE"


def test_text_with_a_missing_value_is_a_bug():
    with pytest.raises(KeyError):
        load_labels("English").text("article_count_other", count=12)


def test_placeholders_never_read_attributes(shipped):
    # With str.format, "{minutes.__class__}" would read an attribute. Template only replaces names.
    shipped["fr"]["article_count_other"] = "$count $minutes.__class__.__mro__"
    labels = load_labels("French")
    assert labels.text("article_count_other", count=2, minutes=3) == "2 3.__class__.__mro__"


@pytest.mark.parametrize(
    ("day", "english", "french"),
    [
        (date(2026, 10, 6), "Tuesday 6 October", "mardi 6 octobre"),
        (date(2026, 10, 5), "Monday 5 October", "lundi 5 octobre"),
        (date(2026, 1, 4), "Sunday 4 January", "dimanche 4 janvier"),
        (date(2026, 12, 31), "Thursday 31 December", "jeudi 31 décembre"),
    ],
)
def test_dates_are_written_without_the_system_locale(day, english, french):
    assert load_labels("English").date(day) == english
    assert load_labels("French").date(day) == french
