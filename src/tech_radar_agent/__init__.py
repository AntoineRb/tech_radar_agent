import argparse
import logging
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

import yaml

from tech_radar_agent.agent.digest import select_entries
from tech_radar_agent.agent.loop import LoopReport, score_and_summarize
from tech_radar_agent.agent.render import render_digest, render_empty_report
from tech_radar_agent.agent.scoring import Scorer
from tech_radar_agent.agent.settings import load_agent_settings
from tech_radar_agent.agent.summary import Summarizer
from tech_radar_agent.collectors import Collector, build_collector
from tech_radar_agent.config import Config, Profile, load_config
from tech_radar_agent.delivery.preview import write_preview
from tech_radar_agent.delivery.telegram import (
    OutgoingMessage,
    TelegramClient,
    load_telegram_settings,
    pack_messages,
    send_digest,
)
from tech_radar_agent.i18n import load_labels
from tech_radar_agent.llm import load_llm_settings
from tech_radar_agent.llm.client import LlmClient
from tech_radar_agent.storage import best_recent_score, connect, fetch_digest_candidates, mark_sent, save_articles

logger = logging.getLogger(__name__)

# Process exit codes, useful to spot a broken run in CI. When several problems happen, the earliest
# (the broadest) is reported: 1, then 3, then 4.
EXIT_OK = 0
EXIT_ALL_SOURCES_FAILED = 1
EXIT_CONFIG_ERROR = 2
EXIT_SCORING_STOPPED = 3  # The collection is saved, but scoring could not run to the end (ADR 0019).
EXIT_DIGEST_NOT_SENT = 4  # Telegram not configured, sending failed, or only part of the digest went out.


@dataclass(frozen=True)
class CollectionReport:
    failed: list[str]  # Names of the sources that failed.
    new_articles: int  # Articles added to the database by this run.


def parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="tech-radar-agent", description="Collect, score and summarize tech news, then send the digest on Telegram."
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="do everything (collect, score with the LLM) but send nothing and mark nothing as sent; "
        "write the digest to output/ instead",
    )
    mode.add_argument(
        "--preview",
        action="store_true",
        help="only build the digest from what is already in the database (no collection, no LLM call), "
        "write it to output/; nothing sent or marked",
    )
    mode.add_argument(
        "--send-only",
        action="store_true",
        help="only send the digest of what is already in the database (no collection, no LLM call); "
        "its articles are marked as sent, like in a normal run",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the pipeline once: collect, score and summarize, then send the digest. Return the exit code."""
    args = parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Otherwise one log line per HTTP request.

    # A config error stops the run before any network call: it has to be fixed, not skipped.
    try:
        config = load_config()
        digest_only = args.preview or args.send_only  # No collection, no LLM: the digest from the database.
        collectors = [] if digest_only else build_collectors(config.sources)
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        logger.error("Invalid configuration: %s", error)
        return EXIT_CONFIG_ERROR

    conn = connect()
    try:
        if digest_only:
            # This run collected and scored nothing: the report of an empty day says so (0 and 0).
            delivered = build_and_deliver_digest(conn, config, new_articles=0, scored=0, write_only=args.preview)
            return EXIT_OK if delivered else EXIT_DIGEST_NOT_SENT

        collection = collect_all(conn, collectors)
        # Scoring runs even when every source failed: articles left unscored by an earlier run still count.
        scoring = score_new_articles(conn, config.profile)
        # The digest goes out even when scoring stopped: articles scored before still deserve it.
        delivered = build_and_deliver_digest(
            conn,
            config,
            new_articles=collection.new_articles,
            scored=scoring.scored if scoring else 0,
            write_only=args.dry_run,
        )
    finally:
        conn.close()

    if len(collection.failed) == len(collectors):
        return EXIT_ALL_SOURCES_FAILED
    if scoring is None or scoring.stopped:
        return EXIT_SCORING_STOPPED
    return EXIT_OK if delivered else EXIT_DIGEST_NOT_SENT


def build_collectors(sources: list[dict[str, Any]]) -> list[Collector]:
    """Create one collector per configured source, checking that source names are unique."""
    collectors = [build_collector(source) for source in sources]
    duplicates = [name for name, count in Counter(c.name for c in collectors).items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate source names {duplicates}: give each source a distinct `name`")
    return collectors


def collect_all(conn: sqlite3.Connection, collectors: list[Collector]) -> CollectionReport:
    """Run every collector and save its articles. Return the failed sources and the number of new articles."""
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
    return CollectionReport(failed=failed, new_articles=added)


def score_new_articles(conn: sqlite3.Connection, profile: Profile) -> LoopReport | None:
    """Score and summarize the articles waiting for it. Return the report, or None if scoring was skipped.

    Read after the collection on purpose (ADR 0018): a missing or invalid LLM setup must not cost the
    day's collection, which is already saved when this runs.
    """
    try:
        llm_settings = load_llm_settings()
        agent_settings = load_agent_settings()
    except ValueError as error:  # The message names the variable, never its value for the API key.
        logger.error("Scoring skipped, invalid LLM or agent settings: %s", error)
        return None

    with LlmClient(llm_settings) as llm:
        report = score_and_summarize(
            conn,
            Scorer(llm, profile),
            Summarizer(llm, profile),
            agent_settings,
            model=llm_settings.model,
        )
    log_report(report, llm_settings.model)
    return report


def log_report(report: LoopReport, model: str) -> None:
    """One summary line for the scoring pass. The reason of an early stop is logged by the loop itself."""
    logger.info(
        "Scoring with %s: %d/%d articles scored (%d summarized, %d summary failures), %d failed%s",
        model, report.scored, report.total, report.summarized, report.summary_failed, report.score_failed,
        f", stopped early: {report.remaining} left for the next run" if report.stopped else "",
    )


def build_and_deliver_digest(
    conn: sqlite3.Connection, config: Config, *, new_articles: int, scored: int, write_only: bool
) -> bool:
    """Select, render and send today's digest (or the report of a day with no candidate).

    write_only (--dry-run, --preview): write it to output/ instead; nothing is sent or marked, and
    Telegram does not need to be configured. Return True if the digest went out entirely (or was written,
    or there was nothing to send), False otherwise: settings missing, sending failed or partial.
    """
    try:
        agent_settings = load_agent_settings()  # Same threshold and age window as scoring.
    except ValueError as error:
        logger.error("Digest skipped, invalid agent settings: %s", error)
        return False

    labels = load_labels(config.profile.language)
    today = date.today()
    candidates = fetch_digest_candidates(conn, agent_settings.summary_threshold, agent_settings.max_article_age_days)
    blocks = render_digest(select_entries(candidates, config.digest.reading_time_minutes), labels, today)

    if blocks:
        messages = pack_messages(blocks)
    elif config.digest.send_empty_report:
        best = best_recent_score(conn, agent_settings.max_article_age_days)
        report = render_empty_report(labels, agent_settings.summary_threshold, new_articles, scored, best)
        messages = [OutgoingMessage(report, ())]
    else:
        logger.info("Digest: nothing to send today (digest.send_empty_report is off)")
        return True

    article_count = sum(len(message.article_ids) for message in messages)
    if write_only:
        path = write_preview(messages, today)
        logger.info(
            "Digest written to %s (%d articles, %d messages): not sent, nothing marked",
            path, article_count, len(messages),
        )
        return True

    try:
        telegram_settings = load_telegram_settings()
    except ValueError as error:  # Names the variable, never the token.
        logger.error("Digest not sent, invalid Telegram settings: %s", error)
        return False

    with TelegramClient(telegram_settings) as client:
        # Each message's articles are marked as sent once Telegram confirmed it, and never before.
        delivery = send_digest(client, messages, lambda article_ids: mark_sent(conn, article_ids))
    logger.info(
        "Digest: %d/%d messages sent (%d articles in the digest), %d refused%s",
        delivery.sent, delivery.total, article_count, delivery.failed,
        f", stopped: {delivery.stop_reason}" if delivery.stop_reason else "",
    )
    return delivery.complete
