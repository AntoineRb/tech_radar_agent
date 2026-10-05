"""The agent loop: score recent articles, summarize the best ones, save everything as it goes (ADR 0018-0020).

    call_with_retry(call, sleep=...)                                     -> whatever `call` returns
    score_and_summarize(conn, scorer, summarizer, settings, model=...)  -> LoopReport

For each article to score (fetch_articles_to_score), newest first:
    score -> if score >= threshold: summarize -> save_score -> save_summary (unless the summary is None)

Failure handling (ADR 0019): the client CLASSIFIES errors, this loop DECIDES what to do with them.
- LlmError itself, ScoreValidationError, SummaryValidationError: about this one article. Skip it and go on.
  A failed scoring leaves the article unscored, retried at the next run; a failed summary keeps the
  score without a summary (retrying would give the same answer at temperature 0). MAX_CONSECUTIVE_FAILURES
  scoring failures in a row stop the loop: something global is wrong.
- LlmTemporaryError: retried after RETRY_DELAYS (or the server's retry_after), then the loop stops.
- LlmFatalError: the loop stops at once.
A stop saves nothing for the article it happened on, even during its summary: that article stays
unscored and is processed again, from scratch, at the next run. Everything saved before stays saved
(each save_* commits at once). Any other exception is a bug and propagates.
"""

import logging
import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from tech_radar_agent.agent.scoring import Scorer
from tech_radar_agent.agent.settings import AgentSettings
from tech_radar_agent.agent.summary import Summarizer
from tech_radar_agent.llm.client import LlmError, LlmFatalError, LlmTemporaryError
from tech_radar_agent.storage.database import fetch_articles_to_score, save_score, save_summary

logger = logging.getLogger(__name__)

T = TypeVar("T")  # What the retried call returns: Score for scoring, str | None for a summary.

# --- Failure guards (ADR 0019) ---
MAX_CONSECUTIVE_FAILURES = 5  # Scoring failures in a row: likely global (broken prompt, model), so stop.
RETRY_DELAYS = (2.0, 8.0)  # Seconds to wait before the 2nd, then the 3rd attempt after a temporary error.
MAX_RETRY_AFTER = 60.0  # Cap on the server's Retry-After: a buggy or hostile server must not block the run.


# --- Run report ---


@dataclass(frozen=True)
class LoopReport:
    """Summary of one run of the scoring loop, for main().

    Each article to score ends up in exactly one of: scored, score_failed, remaining.
    The summary counters only count scored articles, and not all of them: an article below the
    threshold, or whose summary is None (too little content), is in neither. So
    summarized + summary_failed <= scored.

    Attributes:
        total: Number of articles to score when the loop started.
        scored: Articles scored and saved, whatever happened to their summary.
        score_failed: Articles whose scoring failed with an error specific to them. Left unscored,
            retried at the next run.
        summarized: Scored articles whose summary was saved.
        summary_failed: Scored articles whose summary failed with an error specific to them (e.g. an
            invalid answer). Their score is saved without a summary: retrying would give the same
            answer (temperature 0).
        stop_reason: Why the loop stopped early, or None if it ran to the end.
    """

    total: int
    scored: int
    score_failed: int
    summarized: int
    summary_failed: int
    stop_reason: str | None = None

    @property
    def stopped(self) -> bool:
        """Whether the loop stopped before going through every article."""
        return self.stop_reason is not None

    @property
    def remaining(self) -> int:
        """Articles left unscored by an early stop.

        The articles never reached, plus the one the loop stopped on after a fatal error or a
        temporary error that outlasted the retries. Whether that stop happened while scoring or while
        summarizing it, nothing is saved for that article: it stays unscored and is processed again,
        from scratch, at the next run.

        A stop after MAX_CONSECUTIVE_FAILURES scoring failures is different: the last failed article
        is already counted in `score_failed`, so only the articles never reached are remaining.
        """
        return self.total - self.scored - self.score_failed


# --- Retrying temporary errors ---


def call_with_retry(call: Callable[[], T], *, sleep: Callable[[float], None] = time.sleep) -> T:
    """Call `call`, retrying only on temporary LLM errors.

    The call is tried once, then once more after each delay in RETRY_DELAYS.
    A server-provided `retry_after` replaces the default delay, capped at
    MAX_RETRY_AFTER because the server is not a trustworthy source.

    Args:
        call: A function with no argument, typically a lambda.
        sleep: Injected so tests can record waits instead of sleeping.

    Returns:
        Whatever `call` returns.

    Raises:
        LlmTemporaryError: If every attempt failed (the last error is raised).
        Exception: Any other exception from `call`, immediately, without retry.
    """
    attempts = len(RETRY_DELAYS) + 1
    for attempt, default_delay in enumerate(RETRY_DELAYS, start=1):
        try:
            return call()
        except LlmTemporaryError as error:
            if error.retry_after is not None:
                delay = min(error.retry_after, MAX_RETRY_AFTER)
            else:
                delay = default_delay
            logger.warning(
                "Temporary LLM error on attempt %d/%d (%s), retrying in %.1f s", attempt, attempts, error, delay
            )
            sleep(delay)
    # Last attempt, outside the try: if it fails, its error propagates as is.
    return call()


# --- The loop ---


def score_and_summarize(
    conn: sqlite3.Connection,
    scorer: Scorer,
    summarizer: Summarizer,
    settings: AgentSettings,
    *,
    model: str,
    sleep: Callable[[float], None] = time.sleep,
) -> LoopReport:
    """Score recent unscored articles, then summarize the best ones.

    Args:
        conn: Open database connection.
        scorer: Rates an article from 0 to 10.
        summarizer: Summarizes an article.
        settings: Age window, per-run limit and summary threshold.
        model: Model name, stored in `scored_with`.
        sleep: Injected so tests can record waits instead of sleeping.

    Returns:
        A report of what happened. Never raises an LLM exception: an early
        stop is reported through `stop_reason`.
    """
    articles = fetch_articles_to_score(
        conn, settings.max_article_age_days, settings.max_articles_per_run
    )

    scored = 0
    score_failed = 0
    summarized = 0
    summary_failed = 0
    consecutive_failures = 0
    stop_reason: str | None = None

    for stored in articles:
        article = stored.article

        # Scoring
        try:
            result = call_with_retry(lambda: scorer.score(article), sleep=sleep)
        except (LlmTemporaryError, LlmFatalError) as error:
            # Before LlmError: these are subclasses of it
            stop_reason = f"{type(error).__name__}: {error}"
            break
        except LlmError as error:
            score_failed += 1
            consecutive_failures += 1
            # The message is safe to log: validation errors never echo the LLM answer.
            logger.warning("Scoring failed for %r: %s (%s)", article.title, type(error).__name__, error)
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                stop_reason = f"{consecutive_failures} consecutive scoring failures"
                break
            continue
        consecutive_failures = 0

        # Summary
        summary: str | None = None
        if result.score >= settings.summary_threshold:
            try:
                summary = call_with_retry(lambda: summarizer.summarize(article), sleep=sleep)
            except (LlmTemporaryError, LlmFatalError) as error:
                stop_reason = f"{type(error).__name__}: {error}"
                break
            except LlmError as error:
                summary_failed += 1
                logger.warning("Summary failed for %r: %s (%s)", article.title, type(error).__name__, error)

        # Saving
        save_score(
            conn,
            stored.id,
            score=result.score,
            reason=result.reason,
            interests=result.interests,
            scored_with=model,
        )
        scored += 1
        if summary is not None:
            save_summary(conn, stored.id, summary)
            summarized += 1

    if stop_reason is not None:
        logger.error("Scoring stopped: %s", stop_reason)

    return LoopReport(
        total=len(articles),
        scored=scored,
        score_failed=score_failed,
        summarized=summarized,
        summary_failed=summary_failed,
        stop_reason=stop_reason,
    )
