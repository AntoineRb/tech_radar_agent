"""Tests for agent/loop.py. No LLM and no real waiting are involved:
- a real SQLite database in tmp_path, filled with save_articles and read back with SELECT;
- FakeScorer / FakeSummarizer return (or raise) an answer chosen per article title, and record their calls;
- `sleep` is replaced by `waits.append`, which records each wait instead of sleeping.

Run one group only: uv run pytest tests/agent/test_loop.py -k retry
"""

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from tech_radar_agent.agent.loop import (
    MAX_CONSECUTIVE_FAILURES,
    MAX_RETRY_AFTER,
    RETRY_DELAYS,
    LoopReport,
    call_with_retry,
    score_and_summarize,
)
from tech_radar_agent.agent.scoring import Score, ScoreValidationError
from tech_radar_agent.agent.settings import AgentSettings
from tech_radar_agent.agent.summary import SummaryValidationError
from tech_radar_agent.llm.client import LlmError, LlmFatalError, LlmTemporaryError
from tech_radar_agent.models import Article
from tech_radar_agent.storage import connect, save_articles

THRESHOLD = 8


def score(value: int = 5) -> Score:
    """A valid Score: the loop only reads it and saves it."""
    return Score(score=value, reason="Matches the Python interest.", interests=("python",))


class FakeScorer:
    """Stands in for Scorer. `replies` maps a title to a Score, an exception to raise, or a list of
    those consumed one per call (to simulate a temporary error followed by a success)."""

    def __init__(self, replies: dict[str, Any]) -> None:
        self.replies = replies
        self.calls: list[str] = []

    def _reply(self, article: Article) -> Any:
        self.calls.append(article.title)
        reply = self.replies[article.title]
        if isinstance(reply, list):
            reply = reply.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    def score(self, article: Article) -> Score:
        return self._reply(article)


class FakeSummarizer(FakeScorer):
    """Stands in for Summarizer: a summary (str), None, or an exception, per title."""

    def summarize(self, article: Article) -> str | None:
        return self._reply(article)


@pytest.fixture
def conn(tmp_path):
    connection = connect(tmp_path / "test.db")
    yield connection
    connection.close()


def add_articles(conn: sqlite3.Connection, *titles: str, days_ago: float = 0) -> None:
    """Store articles whose fetch order (newest first) is the order of `titles`."""
    now = datetime.now(timezone.utc)
    save_articles(
        conn,
        [
            Article(
                source="test",
                title=title,
                url=f"https://example.com/{title}",
                published_at=now - timedelta(days=days_ago, minutes=index),
            )
            for index, title in enumerate(titles)
        ],
    )


def run(
    conn: sqlite3.Connection,
    scores: dict[str, Any],
    summaries: dict[str, Any] | None = None,
    **settings: int,
) -> tuple[LoopReport, FakeScorer, FakeSummarizer, list[float]]:
    """Run the loop with fakes, and check the report's invariants on every run."""
    scorer, summarizer, waits = FakeScorer(scores), FakeSummarizer(summaries or {}), []
    report = score_and_summarize(
        conn,
        scorer,  # type: ignore[arg-type]
        summarizer,  # type: ignore[arg-type]
        AgentSettings(**({"summary_threshold": THRESHOLD} | settings)),
        model="test-model",
        sleep=waits.append,
    )
    assert report.scored + report.score_failed + report.remaining == report.total
    assert report.summarized + report.summary_failed <= report.scored
    return report, scorer, summarizer, waits


def row(conn: sqlite3.Connection, title: str) -> sqlite3.Row:
    return conn.execute(
        "SELECT score, reason, interests, summary, scored_at, scored_with FROM articles WHERE title = ?", (title,)
    ).fetchone()


def is_unscored(conn: sqlite3.Connection, title: str) -> bool:
    """Nothing at all was saved for this article: it will be picked up again at the next run."""
    saved = row(conn, title)
    return all(saved[column] is None for column in ("score", "reason", "interests", "summary", "scored_at"))


# --- call_with_retry ---


class FakeCall:
    """A call that raises the given errors in turn, then returns "ok"."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.count = 0

    def __call__(self) -> str:
        self.count += 1
        if self.errors:
            raise self.errors.pop(0)
        return "ok"


def test_retry_returns_result_without_waiting():
    call, waits = FakeCall(), []
    assert call_with_retry(call, sleep=waits.append) == "ok"
    assert call.count == 1
    assert waits == []


def test_retry_succeeds_after_temporary_errors(caplog):
    call, waits = FakeCall(LlmTemporaryError("HTTP 503"), LlmTemporaryError("HTTP 503")), []
    with caplog.at_level(logging.WARNING):
        assert call_with_retry(call, sleep=waits.append) == "ok"
    assert call.count == 3
    assert waits == list(RETRY_DELAYS)
    assert "attempt 1/3" in caplog.text and "attempt 2/3" in caplog.text


def test_retry_gives_up_after_all_attempts():
    errors = [LlmTemporaryError(f"HTTP 503 #{n}") for n in range(len(RETRY_DELAYS) + 1)]
    call, waits = FakeCall(*errors), []
    with pytest.raises(LlmTemporaryError) as raised:
        call_with_retry(call, sleep=waits.append)
    assert raised.value is errors[-1]  # The LAST error is the one raised.
    assert call.count == len(RETRY_DELAYS) + 1
    assert waits == list(RETRY_DELAYS)  # No wait after the last attempt.


@pytest.mark.parametrize("retry_after", [5.0, 0.0])  # 0.0 is a real value, not "absent".
def test_retry_uses_retry_after_when_given(retry_after):
    call, waits = FakeCall(LlmTemporaryError("HTTP 429", retry_after=retry_after)), []
    assert call_with_retry(call, sleep=waits.append) == "ok"
    assert waits == [retry_after]


def test_retry_after_is_capped():
    """A buggy or hostile server must not block the run for a day."""
    call, waits = FakeCall(LlmTemporaryError("HTTP 429", retry_after=86400)), []
    call_with_retry(call, sleep=waits.append)
    assert waits == [MAX_RETRY_AFTER]


@pytest.mark.parametrize(
    "error",
    [
        LlmFatalError("HTTP 401"),
        LlmError("LLM returned an empty response"),
        ScoreValidationError("LLM answer is not valid JSON"),
        SummaryValidationError("summary contains a link or HTML"),
        RuntimeError("a bug"),
    ],
)
def test_retry_does_not_retry_other_errors(error):
    call, waits = FakeCall(error), []
    with pytest.raises(type(error)):
        call_with_retry(call, sleep=waits.append)
    assert call.count == 1
    assert waits == []


# --- score_and_summarize: normal runs ---


def test_nothing_to_score_makes_no_llm_call(conn):
    add_articles(conn, "old", days_ago=10)  # Outside the recency window.
    report, scorer, summarizer, _ = run(conn, {"old": score(9)})
    assert report == LoopReport(total=0, scored=0, score_failed=0, summarized=0, summary_failed=0)
    assert scorer.calls == [] and summarizer.calls == []
    assert is_unscored(conn, "old")


def test_settings_window_and_limit_are_used(conn):
    add_articles(conn, "new1", "new2", "new3")
    add_articles(conn, "old", days_ago=5)
    replies = {title: score() for title in ("new1", "new2", "new3", "old")}
    report, scorer, _, _ = run(conn, replies, max_articles_per_run=2, max_article_age_days=3)
    assert scorer.calls == ["new1", "new2"]  # Newest first, at most 2, never the old one.
    assert report.total == 2


def test_scores_are_saved(conn):
    add_articles(conn, "a")
    run(conn, {"a": Score(score=6, reason="Useful for CI.", interests=("python", "ci"))})
    saved = row(conn, "a")
    assert saved["score"] == 6
    assert saved["reason"] == "Useful for CI."
    assert json.loads(saved["interests"]) == ["python", "ci"]
    assert saved["scored_with"] == "test-model"
    assert datetime.fromisoformat(saved["scored_at"]).tzinfo is not None
    assert saved["summary"] is None  # Below the threshold.


def test_summary_only_at_or_above_threshold(conn):
    add_articles(conn, "seven", "eight", "nine")
    report, _, summarizer, _ = run(
        conn,
        {"seven": score(7), "eight": score(8), "nine": score(9)},
        {"eight": "Summary of eight.", "nine": "Summary of nine."},
    )
    assert summarizer.calls == ["eight", "nine"]  # 8 == threshold: summarized.
    assert row(conn, "seven")["summary"] is None
    assert row(conn, "eight")["summary"] == "Summary of eight."
    assert row(conn, "nine")["summary"] == "Summary of nine."
    assert report.summarized == 2


def test_none_summary_is_not_saved(conn):
    add_articles(conn, "short")
    report, _, summarizer, _ = run(conn, {"short": score(9)}, {"short": None})
    assert summarizer.calls == ["short"]
    assert row(conn, "short")["score"] == 9
    assert row(conn, "short")["summary"] is None
    assert (report.scored, report.summarized, report.summary_failed) == (1, 0, 0)


def test_report_counts(conn):
    add_articles(conn, "low", "summarized", "nothing", "bad-summary", "bad-score")
    report, _, _, _ = run(
        conn,
        {
            "low": score(3),
            "summarized": score(9),
            "nothing": score(9),
            "bad-summary": score(8),
            "bad-score": ScoreValidationError("LLM answer is not valid JSON"),
        },
        {"summarized": "A summary.", "nothing": None, "bad-summary": SummaryValidationError("link")},
    )
    assert report == LoopReport(total=5, scored=4, score_failed=1, summarized=1, summary_failed=1)
    assert not report.stopped
    assert report.remaining == 0


# --- score_and_summarize: failures ---


def test_article_error_skips_article_and_continues(conn, caplog):
    add_articles(conn, "a", "b", "c")
    with caplog.at_level(logging.WARNING):
        report, scorer, _, _ = run(
            conn, {"a": score(), "b": ScoreValidationError("LLM answer is not valid JSON"), "c": score()}
        )
    assert scorer.calls == ["a", "b", "c"]
    assert is_unscored(conn, "b")  # Retried at the next run.
    assert row(conn, "c")["score"] == 5
    assert (report.scored, report.score_failed, report.stop_reason) == (2, 1, None)
    assert "'b'" in caplog.text and "not valid JSON" in caplog.text


def test_consecutive_article_errors_stop_the_loop(conn):
    titles = [f"t{n}" for n in range(MAX_CONSECUTIVE_FAILURES + 2)]
    add_articles(conn, *titles)
    report, scorer, _, _ = run(conn, {title: ScoreValidationError("bad") for title in titles})
    assert scorer.calls == titles[:MAX_CONSECUTIVE_FAILURES]  # The last two are never called.
    assert report.stopped
    assert report.score_failed == MAX_CONSECUTIVE_FAILURES  # The last failed one is in score_failed...
    assert report.remaining == 2  # ...so only the articles never reached remain.


def test_success_resets_consecutive_errors(conn):
    fails = MAX_CONSECUTIVE_FAILURES - 1
    titles = [f"t{n}" for n in range(2 * fails + 1)]
    add_articles(conn, *titles)
    replies: dict[str, Any] = {title: ScoreValidationError("bad") for title in titles}
    replies[titles[fails]] = score()  # One success in the middle.
    report, scorer, _, _ = run(conn, replies)
    assert not report.stopped
    assert scorer.calls == titles
    assert (report.scored, report.score_failed) == (1, 2 * fails)


def test_summary_errors_do_not_count_as_consecutive_failures(conn):
    """Option B: only scoring failures stop the loop; a broken summary shows in summary_failed."""
    # A summary failure right before MAX - 1 scoring failures: counting it would make MAX in a row.
    # (A run of summary failures alone would not show the bug: each valid score resets the counter.)
    failing = [f"t{n}" for n in range(MAX_CONSECUTIVE_FAILURES - 1)]
    add_articles(conn, "summary-fails", *failing)
    replies: dict[str, Any] = {title: ScoreValidationError("bad") for title in failing}
    replies["summary-fails"] = score(9)
    report, scorer, _, _ = run(conn, replies, {"summary-fails": SummaryValidationError("link")})
    assert not report.stopped
    assert scorer.calls == ["summary-fails", *failing]
    assert (report.scored, report.summary_failed, report.score_failed) == (1, 1, len(failing))


def test_fatal_error_stops_immediately(conn, caplog):
    add_articles(conn, "a", "b", "c")
    with caplog.at_level(logging.ERROR):
        report, scorer, _, waits = run(conn, {"a": score(), "b": LlmFatalError("HTTP 401"), "c": score()})
    assert scorer.calls == ["a", "b"]
    assert waits == []  # Never retried.
    assert row(conn, "a")["score"] == 5  # Kept.
    assert is_unscored(conn, "b") and is_unscored(conn, "c")
    assert report.stopped and "LlmFatalError" in report.stop_reason and "HTTP 401" in report.stop_reason
    assert report.remaining == 2
    assert "Scoring stopped" in caplog.text


def test_temporary_error_exhausted_stops_the_loop(conn):
    add_articles(conn, "a", "b", "c")
    attempts = len(RETRY_DELAYS) + 1
    report, scorer, _, waits = run(
        conn, {"a": score(), "b": [LlmTemporaryError("HTTP 503")] * attempts, "c": score()}
    )
    assert scorer.calls == ["a"] + ["b"] * attempts
    assert waits == list(RETRY_DELAYS)
    assert row(conn, "a")["score"] == 5
    assert is_unscored(conn, "b") and is_unscored(conn, "c")
    assert report.stopped and "LlmTemporaryError" in report.stop_reason
    assert report.remaining == 2


def test_temporary_error_then_success_is_not_a_failure(conn):
    add_articles(conn, "a")
    report, scorer, _, waits = run(conn, {"a": [LlmTemporaryError("HTTP 429", retry_after=1.0), score()]})
    assert scorer.calls == ["a", "a"]
    assert waits == [1.0]
    assert (report.scored, report.score_failed, report.stopped) == (1, 0, False)


def test_summary_error_keeps_the_score(conn, caplog):
    """Decision A: an invalid summary would be the same on retry (temperature 0), so the score is saved."""
    add_articles(conn, "a", "b")
    with caplog.at_level(logging.WARNING):
        report, _, summarizer, _ = run(
            conn, {"a": score(9), "b": score(9)}, {"a": SummaryValidationError("summary contains a link or HTML"), "b": "Ok."}
        )
    assert summarizer.calls == ["a", "b"]  # The loop went on.
    assert row(conn, "a")["score"] == 9
    assert row(conn, "a")["summary"] is None
    assert row(conn, "b")["summary"] == "Ok."
    assert (report.scored, report.summarized, report.summary_failed, report.stopped) == (2, 1, 1, False)
    assert "'a'" in caplog.text and "link or HTML" in caplog.text


@pytest.mark.parametrize(
    "failure",
    [
        [LlmFatalError("server down")],
        [LlmTemporaryError("HTTP 503")] * (len(RETRY_DELAYS) + 1),
    ],
    ids=["fatal", "temporary-exhausted"],
)
def test_stop_during_summary_saves_nothing_for_that_article(conn, failure):
    """Decision D: the server is down, so the article is left unscored and redone at the next run."""
    add_articles(conn, "a", "b", "c")
    report, scorer, _, _ = run(
        conn, {"a": score(9), "b": score(9), "c": score(9)}, {"a": "Summary of a.", "b": failure}
    )
    assert scorer.calls == ["a", "b"]  # "c" is never reached.
    assert row(conn, "a")["summary"] == "Summary of a."
    assert is_unscored(conn, "b")  # Its score was NOT saved.
    assert is_unscored(conn, "c")
    assert report.stopped
    assert (report.scored, report.summarized, report.summary_failed, report.remaining) == (1, 1, 0, 2)


def test_unexpected_exception_is_not_swallowed(conn):
    """A bug in our code must crash loudly, not be counted as an article failure."""
    add_articles(conn, "a", "b")
    with pytest.raises(RuntimeError, match="a bug"):
        run(conn, {"a": score(), "b": RuntimeError("a bug")})
    assert row(conn, "a")["score"] == 5  # What was saved before the crash is kept.
