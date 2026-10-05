import logging
import sqlite3
from collections import Counter
from typing import Any

import yaml

from tech_radar_agent.agent.loop import LoopReport, score_and_summarize
from tech_radar_agent.agent.scoring import Scorer
from tech_radar_agent.agent.settings import load_agent_settings
from tech_radar_agent.agent.summary import Summarizer
from tech_radar_agent.collectors import Collector, build_collector
from tech_radar_agent.config import Profile, load_config
from tech_radar_agent.llm import load_llm_settings
from tech_radar_agent.llm.client import LlmClient
from tech_radar_agent.storage import connect, save_articles

logger = logging.getLogger(__name__)

# Process exit codes, useful to spot a broken run in CI.
EXIT_OK = 0
EXIT_ALL_SOURCES_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_SCORING_STOPPED = 3  # The collection is saved, but scoring could not run to the end (ADR 0019).


def main() -> int:
    """Run the pipeline once: collect from every source, then score and summarize. Return the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Otherwise one log line per HTTP request.

    # A config error stops the run before any network call: it has to be fixed, not skipped.
    try:
        config = load_config()
        collectors = build_collectors(config.sources)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        logger.error("Invalid configuration: %s", error)
        return EXIT_CONFIG_ERROR

    conn = connect()
    try:
        failed = collect_all(conn, collectors)
        # Scoring runs even when every source failed: articles left unscored by an earlier run still count.
        scoring_completed = score_new_articles(conn, config.profile)
    finally:
        conn.close()

    # A collection failure is reported first: it is the earlier, broader problem.
    if len(failed) == len(collectors):
        return EXIT_ALL_SOURCES_FAILED
    return EXIT_OK if scoring_completed else EXIT_SCORING_STOPPED


def build_collectors(sources: list[dict[str, Any]]) -> list[Collector]:
    """Create one collector per configured source, checking that source names are unique."""
    collectors = [build_collector(source) for source in sources]
    duplicates = [name for name, count in Counter(c.name for c in collectors).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate source names {duplicates}: give each source a distinct `name`")
    return collectors


def collect_all(conn: sqlite3.Connection, collectors: list[Collector]) -> list[str]:
    """Run every collector and save its articles. Return the names of the sources that failed."""
    failed = []
    collected = added = 0
    for collector in collectors:
        try:
            articles = collector.collect()
        except Exception:  # One broken source must not stop the others.
            logger.exception("%s: source failed, skipping it", collector.name)
            failed.append(collector.name)
            continue
        new = save_articles(conn, articles)  # Saved per source, so a later crash loses nothing.
        collected += len(articles)
        added += new
        logger.info("%s: %d new articles", collector.name, new)

    logger.info(
        "Done: %d articles collected, %d new, %d/%d sources failed%s",
        collected, added, len(failed), len(collectors), f" ({', '.join(failed)})" if failed else "",
    )
    return failed


def score_new_articles(conn: sqlite3.Connection, profile: Profile) -> bool:
    """Score and summarize the articles waiting for it. Return False if scoring did not run to the end.

    Read after the collection on purpose (ADR 0018): a missing or invalid LLM setup must not cost the
    day's collection, which is already saved when this runs.
    """
    try:
        llm_settings = load_llm_settings()
        agent_settings = load_agent_settings()
    except ValueError as error:  # The message names the variable, never its value for the API key.
        logger.error("Scoring skipped, invalid LLM or agent settings: %s", error)
        return False

    with LlmClient(llm_settings) as llm:
        report = score_and_summarize(
            conn,
            Scorer(llm, profile),
            Summarizer(llm, profile),
            agent_settings,
            model=llm_settings.model,
        )
    log_report(report, llm_settings.model)
    return not report.stopped


def log_report(report: LoopReport, model: str) -> None:
    """One summary line for the scoring pass. The reason of an early stop is logged by the loop itself."""
    logger.info(
        "Scoring with %s: %d/%d articles scored (%d summarized, %d summary failures), %d failed%s",
        model, report.scored, report.total, report.summarized, report.summary_failed, report.score_failed,
        f", stopped early: {report.remaining} left for the next run" if report.stopped else "",
    )
