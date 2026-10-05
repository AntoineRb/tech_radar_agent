"""Digest selection: which entries fit in the reader's reading-time budget (ADR 0023).

    reading_seconds(candidate)                  -> float                   estimated cost of one entry
    select_entries(candidates, budget_minutes)  -> list[DigestCandidate]   the entries kept

Candidates come ALREADY in selection order (fetch_digest_candidates: best score first, then oldest
first). This module does not sort: it fills the budget. No LLM, no database, no clock: pure functions.

Rules:
- candidates are taken in order while they fit in the time left;
- a candidate that does not fit is SKIPPED, and selection goes on with the next ones. It is not marked
  as sent, so it competes again for the next digest;
- at least one entry whenever there is a candidate: the best one, even beyond the budget.
"""

from collections.abc import Sequence

from tech_radar_agent.storage import DigestCandidate

READING_SPEED_WPM = 200  # Words per minute, reading on a screen (usual range: 200 to 250).
ENTRY_OVERHEAD_SECONDS = 3  # Fixed cost per entry: spotting the line, its score, its link.


# --- Cost of one entry ---


def reading_seconds(candidate: DigestCandidate) -> float:
    """Estimated time, in seconds, to read one digest entry and decide whether to open the article.

    The text read is the title, plus the summary when there is one, otherwise the reason. Words are
    counted with str.split(), so any run of spaces, tabs or newlines separates two words.
    """
    # The title, plus the summary when there is one, otherwise the reason: what the entry will show.
    text = candidate.summary or candidate.reason
    title_words: int = len(candidate.article.title.split())
    text_words: int = len(text.split())
    total_words: int = title_words + text_words

    # words per second
    reading_speed_wps = READING_SPEED_WPM / 60

    # Words divided by speed gives a time; the fixed cost covers spotting the entry and its link.
    return total_words / reading_speed_wps + ENTRY_OVERHEAD_SECONDS


# --- Filling the budget ---


def select_entries(candidates: Sequence[DigestCandidate], budget_minutes: int) -> list[DigestCandidate]:
    """The digest entries: the best candidates that fit in the reading-time budget.

    Args:
        candidates: in selection order, as returned by fetch_digest_candidates. Never modified.
        budget_minutes: config.digest.reading_time_minutes (a whole number from 1 to 30, already checked).

    Returns:
        The candidates kept, in the same order as given. Empty only when there is no candidate.
        An entry whose cost is exactly the time left is kept.
    """
    if not candidates:
        return []

    total_reading_limit_in_seconds = 60 * budget_minutes
    total_reading_seconds = 0.0
    candidates_selected: list[DigestCandidate] = []

    for candidate in candidates:
        candidate_reading_seconds = reading_seconds(candidate)
        fits = total_reading_seconds + candidate_reading_seconds <= total_reading_limit_in_seconds
        # The first candidate, the best one, is kept even beyond the budget: never an empty digest.
        if not fits and candidates_selected:
            continue  # Skipped, not stopped: a shorter candidate further down may still fit.
        total_reading_seconds += candidate_reading_seconds
        candidates_selected.append(candidate)

    return candidates_selected
