import logging
import sqlite3
from collections import Counter

import yaml

from tech_radar_agent.collectors import Collector, build_collector
from tech_radar_agent.config import load_config
from tech_radar_agent.storage import connect, save_articles

logger = logging.getLogger(__name__)

# Process exit codes, useful to spot a broken run in CI.
EXIT_OK = 0
EXIT_ALL_SOURCES_FAILED = 1
EXIT_CONFIG_ERROR = 2


def main() -> int:
    """Run one collection pass: every source, then save new articles. Return the exit code."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)  # Otherwise one log line per HTTP request.

    # A config error stops the run before any network call: it has to be fixed, not skipped.
    try:
        collectors = build_collectors()
    except (OSError, ValueError, TypeError, yaml.YAMLError) as error:
        logger.error("Invalid configuration: %s", error)
        return EXIT_CONFIG_ERROR

    conn = connect()
    try:
        failed = collect_all(conn, collectors)
    finally:
        conn.close()

    return EXIT_ALL_SOURCES_FAILED if len(failed) == len(collectors) else EXIT_OK


def build_collectors() -> list[Collector]:
    """Create one collector per configured source, checking that source names are unique."""
    collectors = [build_collector(source) for source in load_config().sources]
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
