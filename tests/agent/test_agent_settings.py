from pathlib import Path

import pytest

from tech_radar_agent.agent.settings import (
    DEFAULT_MAX_ARTICLE_AGE_DAYS,
    DEFAULT_MAX_ARTICLES_PER_RUN,
    DEFAULT_SUMMARY_THRESHOLD,
    AgentSettings,
    load_agent_settings,
)

ENV_EXAMPLE = Path(__file__).parents[2] / ".env.example"


def test_defaults_when_nothing_is_set():
    assert load_agent_settings({}) == AgentSettings(
        max_article_age_days=DEFAULT_MAX_ARTICLE_AGE_DAYS,
        max_articles_per_run=DEFAULT_MAX_ARTICLES_PER_RUN,
        summary_threshold=DEFAULT_SUMMARY_THRESHOLD,
    )


def test_default_values():
    assert (DEFAULT_MAX_ARTICLE_AGE_DAYS, DEFAULT_MAX_ARTICLES_PER_RUN, DEFAULT_SUMMARY_THRESHOLD) == (3, 100, 8)


def test_values_from_environment():
    settings = load_agent_settings(
        {"AGENT_MAX_ARTICLE_AGE_DAYS": " 7 ", "AGENT_MAX_ARTICLES_PER_RUN": "20", "AGENT_SUMMARY_THRESHOLD": "6"}
    )
    assert settings == AgentSettings(max_article_age_days=7, max_articles_per_run=20, summary_threshold=6)


@pytest.mark.parametrize("name", ["AGENT_MAX_ARTICLE_AGE_DAYS", "AGENT_MAX_ARTICLES_PER_RUN", "AGENT_SUMMARY_THRESHOLD"])
def test_empty_value_means_default(name):
    assert load_agent_settings({name: "  "}) == AgentSettings()


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("AGENT_MAX_ARTICLE_AGE_DAYS", "three", "whole number"),
        ("AGENT_MAX_ARTICLE_AGE_DAYS", "2.5", "whole number"),
        ("AGENT_MAX_ARTICLE_AGE_DAYS", "0", "between 1 and 365"),
        ("AGENT_MAX_ARTICLES_PER_RUN", "0", "between 1 and 10000"),
        ("AGENT_MAX_ARTICLES_PER_RUN", "-5", "between 1 and 10000"),
        ("AGENT_SUMMARY_THRESHOLD", "11", "between 0 and 10"),
        ("AGENT_SUMMARY_THRESHOLD", "-1", "between 0 and 10"),
    ],
)
def test_invalid_values(name, value, message):
    with pytest.raises(ValueError, match=f"{name}.*{message}"):
        load_agent_settings({name: value})


@pytest.mark.parametrize("threshold", ["0", "10"])
def test_threshold_bounds_are_allowed(threshold):
    assert load_agent_settings({"AGENT_SUMMARY_THRESHOLD": threshold}).summary_threshold == int(threshold)


def test_reads_the_process_environment_by_default(monkeypatch):
    monkeypatch.setenv("AGENT_SUMMARY_THRESHOLD", "9")
    assert load_agent_settings().summary_threshold == 9


def test_env_example_documents_every_setting_with_its_default():
    values = dict(
        line.split("=", 1) for line in ENV_EXAMPLE.read_text().splitlines() if line.startswith("AGENT_")
    )
    assert values == {
        "AGENT_MAX_ARTICLE_AGE_DAYS": str(DEFAULT_MAX_ARTICLE_AGE_DAYS),
        "AGENT_MAX_ARTICLES_PER_RUN": str(DEFAULT_MAX_ARTICLES_PER_RUN),
        "AGENT_SUMMARY_THRESHOLD": str(DEFAULT_SUMMARY_THRESHOLD),
    }
