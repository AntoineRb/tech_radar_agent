"""Tests for main(): collection, then scoring, with fake collectors and a fake LLM server. No network.

The scoring part runs for real (LlmClient, Scorer, Summarizer, the loop); only the HTTP transport of
LlmClient is replaced, by FakeLlmServer.
"""

import json
import logging
import os
import sqlite3
from pathlib import Path

import httpx
import pytest

import tech_radar_agent
from tech_radar_agent import EXIT_ALL_SOURCES_FAILED, EXIT_CONFIG_ERROR, EXIT_OK, EXIT_SCORING_STOPPED, main
from tech_radar_agent.collectors import COLLECTOR_TYPES, Collector
from tech_radar_agent.llm.client import LlmClient
from tech_radar_agent.models import Article

DB_PATH = Path("data/tech_radar.db")
LONG_CONTENT = "Measured results of a new Python release. " * 20  # Long enough to be summarized.


class FakeCollector(Collector):
    """Returns `count` articles, or raises if `fail` is set. No network involved."""

    type = "fake"

    def __init__(self, name: str | None = None, count: int = 1, fail: bool = False, content: str | None = None) -> None:
        super().__init__(name)
        self.count = count
        self.fail = fail
        self.content = content

    def collect(self) -> list[Article]:
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        return [
            Article(
                source=self.name,
                title=f"{self.name} {i}",
                url=f"https://example.com/{self.name}/{i}",
                content=self.content,
            )
            for i in range(self.count)
        ]


class FakeLlmServer:
    """Answers chat completions like a well-behaved LLM, or with `status` if set. Records requests."""

    def __init__(self) -> None:
        self.status: int | None = None
        self.score = 9
        self.requests: list[dict] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status is not None:
            return httpx.Response(self.status, text="error from the fake server")
        # Only the scoring prompt asks for "interests"; only the summary prompt asks for "summary".
        if '"interests"' in body["messages"][0]["content"]:
            answer = {"score": self.score, "reason": "Matches the Python interest.", "interests": ["python"]}
        else:
            answer = {"summary": "A new Python release, with measured speedups."}
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(answer)}}]})


@pytest.fixture(autouse=True)
def workspace(tmp_path, monkeypatch, caplog):
    """Run main() in an empty folder (it uses paths relative to the working directory)."""
    caplog.set_level(logging.INFO)  # pytest's handlers make main()'s basicConfig a no-op.
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    monkeypatch.setitem(COLLECTOR_TYPES, "fake", FakeCollector)


@pytest.fixture(autouse=True)
def llm(monkeypatch) -> FakeLlmServer:
    """A configured LLM by default, answering through a fake server. The real environment is ignored."""
    for name in list(os.environ):
        if name.startswith(("LLM_", "AGENT_")):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-secret")
    server = FakeLlmServer()
    monkeypatch.setattr(
        tech_radar_agent,
        "LlmClient",
        lambda settings: LlmClient(settings, transport=httpx.MockTransport(server.handle)),
    )
    return server


PROFILE = "profile:\n  about: Test user\n  interests:\n    high:\n      python: Python\n"


def run(sources: str, profile: str = PROFILE) -> int:
    """Write a config made of a valid profile (unless given) and `sources`, then run main()."""
    Path("config/interests.yaml").write_text(profile + sources, encoding="utf-8")
    return main()


def stored_sources() -> list[str]:
    with sqlite3.connect(DB_PATH) as conn:
        return [row[0] for row in conn.execute("SELECT source FROM articles ORDER BY id")]


def stored_results() -> list[tuple]:
    with sqlite3.connect(DB_PATH) as conn:
        return conn.execute("SELECT title, score, summary, scored_with FROM articles ORDER BY id").fetchall()


def test_articles_from_every_source_are_saved():
    config = "sources:\n  - {type: fake, name: a, count: 2}\n  - {type: fake, name: b, count: 1}\n"
    assert run(config) == EXIT_OK
    assert stored_sources() == ["a", "a", "b"]


def test_second_run_adds_nothing(caplog):
    config = "sources:\n  - {type: fake, name: a, count: 2}\n"
    run(config)
    assert run(config) == EXIT_OK
    assert len(stored_sources()) == 2
    assert "0 new" in caplog.text


def test_failing_source_does_not_stop_the_others(caplog):
    config = (
        "sources:\n"
        "  - {type: fake, name: before}\n"
        "  - {type: fake, name: broken, fail: true}\n"
        "  - {type: fake, name: after}\n"
    )
    assert run(config) == EXIT_OK
    assert stored_sources() == ["before", "after"]
    assert "broken: source failed" in caplog.text
    assert "1/3 sources failed (broken)" in caplog.text


def test_all_sources_failing():
    config = "sources:\n  - {type: fake, name: x, fail: true}\n  - {type: fake, name: y, fail: true}\n"
    assert run(config) == EXIT_ALL_SOURCES_FAILED


def test_source_with_no_articles_is_not_a_failure():
    assert run("sources:\n  - {type: fake, count: 0}\n") == EXIT_OK


@pytest.mark.parametrize(
    "config",
    [
        pytest.param("sources:\n  - {type: fake}\n  - {type: fake}\n", id="duplicate-names"),
        pytest.param("sources:\n  - {type: twitter}\n", id="unknown-type"),
        pytest.param("sources:\n  - {type: fake, countt: 3}\n", id="misspelled-option"),
        pytest.param("", id="no-sources"),
        pytest.param("sources: [unclosed\n", id="invalid-yaml"),
        pytest.param("sources: !!python/object/apply:os.system ['echo PWNED']\n", id="unsafe-yaml"),
    ],
)
def test_config_errors_stop_before_collecting(config, caplog):
    assert run(config) == EXIT_CONFIG_ERROR
    assert "Invalid configuration" in caplog.text
    assert not DB_PATH.parent.exists()  # Stopped before opening the database.


def test_invalid_profile_stops_before_collecting(caplog):
    assert run("sources:\n  - {type: fake}\n", profile="profile:\n  about: Me\n") == EXIT_CONFIG_ERROR
    assert "profile.interests" in caplog.text
    assert not DB_PATH.parent.exists()


def test_missing_config_file():
    assert main() == EXIT_CONFIG_ERROR


def test_one_bad_entry_stops_everything():
    # Even valid sources are not run: config errors must be fixed, not skipped.
    assert run("sources:\n  - {type: fake, name: ok}\n  - {type: twitter}\n") == EXIT_CONFIG_ERROR
    assert not DB_PATH.exists()


def test_config_error_makes_no_llm_call(llm):
    assert run("sources:\n  - {type: twitter}\n") == EXIT_CONFIG_ERROR
    assert llm.requests == []


# --- Scoring after the collection ---


def test_collected_articles_are_scored_and_summarized(llm, caplog):
    assert run(f"sources:\n  - {{type: fake, name: a, count: 2, content: '{LONG_CONTENT}'}}\n") == EXIT_OK
    summary = "A new Python release, with measured speedups."
    assert stored_results() == [("a 0", 9, summary, "test-model"), ("a 1", 9, summary, "test-model")]
    assert len(llm.requests) == 4  # One scoring call and one summary call per article.
    assert "Scoring with test-model: 2/2 articles scored (2 summarized, 0 summary failures), 0 failed" in caplog.text


def test_articles_below_threshold_are_not_summarized(llm):
    llm.score = 5
    assert run(f"sources:\n  - {{type: fake, name: a, content: '{LONG_CONTENT}'}}\n") == EXIT_OK
    assert stored_results() == [("a 0", 5, None, "test-model")]
    assert len(llm.requests) == 1


def test_second_run_scores_nothing_again(llm):
    config = "sources:\n  - {type: fake, name: a}\n"
    run(config)
    calls = len(llm.requests)
    assert run(config) == EXIT_OK
    assert len(llm.requests) == calls  # Already scored: no new LLM call.


@pytest.mark.parametrize(
    "variable, value",
    [
        ("LLM_BASE_URL", None),  # Not configured at all.
        ("LLM_BASE_URL", "http://llm.example.com/v1"),  # Plain http to a remote host: refused.
        ("AGENT_SUMMARY_THRESHOLD", "eight"),
    ],
)
def test_invalid_settings_skip_scoring_but_keep_the_collection(llm, monkeypatch, caplog, variable, value):
    if value is None:
        monkeypatch.delenv(variable)
    else:
        monkeypatch.setenv(variable, value)
    assert run("sources:\n  - {type: fake, name: a, count: 2}\n") == EXIT_SCORING_STOPPED
    assert stored_sources() == ["a", "a"]  # The collection is saved anyway.
    assert [score for _, score, _, _ in stored_results()] == [None, None]
    assert llm.requests == []
    assert "Scoring skipped" in caplog.text and variable in caplog.text


@pytest.mark.parametrize("status", [401, 404])
def test_fatal_llm_error_stops_scoring_but_keeps_the_collection(llm, caplog, status):
    llm.status = status
    assert run("sources:\n  - {type: fake, name: a, count: 3}\n") == EXIT_SCORING_STOPPED
    assert stored_sources() == ["a", "a", "a"]
    assert [score for _, score, _, _ in stored_results()] == [None, None, None]
    assert len(llm.requests) == 1  # Stopped at once, not tried on every article.
    assert "Scoring stopped" in caplog.text
    assert "0/3 articles scored" in caplog.text and "3 left for the next run" in caplog.text


def test_unscored_articles_are_scored_at_the_next_run(llm):
    config = "sources:\n  - {type: fake, name: a, count: 2}\n"
    llm.status = 401  # Fatal, not 503: a temporary error would really wait 2 + 8 s (retries: test_loop.py).
    llm_down = run(config)
    llm.status = None
    assert llm_down == EXIT_SCORING_STOPPED
    assert run(config) == EXIT_OK
    assert [score for _, score, _, _ in stored_results()] == [9, 9]


def test_all_sources_failed_takes_precedence_but_scoring_still_runs(llm):
    llm.status = 401
    run("sources:\n  - {type: fake, name: a}\n")  # Collected, left unscored.
    llm.status = None
    assert run("sources:\n  - {type: fake, name: a, fail: true}\n") == EXIT_ALL_SOURCES_FAILED
    assert [score for _, score, _, _ in stored_results()] == [9]  # Scored anyway.


def test_all_sources_failed_wins_over_scoring_stopped(llm):
    llm.status = 401
    run("sources:\n  - {type: fake, name: a}\n")  # Collected, left unscored.
    # Both problems at once: every source fails AND scoring stops. The collection failure is reported.
    assert run("sources:\n  - {type: fake, name: a, fail: true}\n") == EXIT_ALL_SOURCES_FAILED


def test_api_key_never_logged(llm, caplog):
    llm.status = 401
    run("sources:\n  - {type: fake, name: a}\n")
    assert caplog.text  # Something was logged...
    assert "sk-test-secret" not in caplog.text  # ...but never the key.
