"""Tests for agent/digest.py: pure functions, so no database and no LLM.

Only what an entry shows before any tap is costed: its title and its reason (ADR 0024). The summary is
folded, so it never counts. Candidates are built so that their cost is known exactly: a one-word title
(its name, used to identify it in the results) plus a reason of a chosen number of words. At 200 words
per minute, a word costs 0.3 s, and each entry has a fixed ENTRY_OVERHEAD_SECONDS on top.

A real reason is at most 300 characters (about 50 words), so a real entry costs at most about 33 s.
Some selection tests use longer, artificial costs to make a rule visible: they say so.

Run one group only: uv run pytest tests/agent/test_digest.py -k select
"""

from typing import Any

import pytest

from tech_radar_agent.agent.digest import ENTRY_OVERHEAD_SECONDS, READING_SPEED_WPM, reading_seconds, select_entries
from tech_radar_agent.models import Article
from tech_radar_agent.storage import DigestCandidate

SECONDS_PER_WORD = 60 / READING_SPEED_WPM


def words(count: int) -> str:
    return "word " * count


def make_candidate(title: str = "Title", summary: str | None = None, reason: str = "Reason.", **overrides: Any):
    article = Article(source="test", title=title, url=f"https://example.com/{title.replace(' ', '-')}")
    fields: dict[str, Any] = {"id": 1, "article": article, "score": 8, "reason": reason, "interests": (), "summary": summary}
    return DigestCandidate(**(fields | overrides))


def entry(name: str, seconds: float) -> DigestCandidate:
    """A candidate named `name` (its one-word title) whose reading cost is exactly `seconds`.

    Only whole word counts exist, so `seconds` must be the fixed cost plus a multiple of 0.3 s:
    multiples of 3 s (6, 9, 30, 54…) always work. The check below catches any other value.
    """
    total_words = round((seconds - ENTRY_OVERHEAD_SECONDS) / SECONDS_PER_WORD)
    # The words go in the reason, the costed text. A summary is added to show it changes nothing.
    candidate = make_candidate(title=name, reason=words(total_words - 1), summary=words(80))
    assert reading_seconds(candidate) == pytest.approx(seconds)  # The helper itself is checked.
    return candidate


def names(candidates: list[DigestCandidate]) -> list[str]:
    return [candidate.article.title for candidate in candidates]


# --- reading_seconds ---


def test_cost_counts_the_title_and_the_reason():
    candidate = make_candidate(title=words(10), reason=words(90), summary=words(50))
    # 100 words (title + reason; the folded summary is not counted) = 30 s, plus the fixed cost.
    assert reading_seconds(candidate) == pytest.approx(30 + ENTRY_OVERHEAD_SECONDS)


@pytest.mark.parametrize("summary", [None, "", "Short summary.", words(80)], ids=["none", "empty", "short", "long"])
def test_the_summary_is_never_counted(summary):
    # Folded in the digest: unfolding it is extra time the reader chose to spend. So an entry with a
    # summary costs exactly what the same entry without one costs.
    without = make_candidate(title=words(10), reason=words(20), summary=None)
    assert reading_seconds(make_candidate(title=words(10), reason=words(20), summary=summary)) == reading_seconds(without)


def test_longer_reason_costs_more():
    assert reading_seconds(make_candidate(reason=words(40))) > reading_seconds(make_candidate(reason=words(10)))


def test_longer_title_costs_more():
    assert reading_seconds(make_candidate(title=words(30))) > reading_seconds(make_candidate(title=words(5)))


def test_cost_counts_words_whatever_the_spacing():
    spaced = make_candidate(title="Python release", reason="one two three four")
    messy = make_candidate(title="Python release", reason="  one\ttwo\n\nthree    four ")
    assert reading_seconds(messy) == reading_seconds(spaced)


def test_cost_is_never_below_the_fixed_cost():
    assert reading_seconds(make_candidate(title="Python", summary=None, reason="Ok.")) > ENTRY_OVERHEAD_SECONDS


# --- select_entries ---


def test_no_candidate_gives_no_entry():
    assert select_entries([], budget_minutes=5) == []


def test_everything_fits_in_a_large_budget():
    candidates = [entry("a", 30), entry("b", 6), entry("c", 45)]
    assert names(select_entries(candidates, budget_minutes=30)) == ["a", "b", "c"]


def test_selection_stops_counting_at_the_budget():
    candidates = [entry("a", 30), entry("b", 27), entry("c", 30)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["a", "b"]  # 57 s used, "c" would make 87.


def test_an_entry_that_exactly_fits_is_kept():
    candidates = [entry("a", 30), entry("b", 30)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["a", "b"]  # 30 + 30 == 60: kept.


def test_an_entry_that_does_not_fit_is_skipped_and_selection_goes_on():
    candidates = [entry("short1", 9), entry("long", 54), entry("short2", 6), entry("short3", 6)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["short1", "short2", "short3"]


def test_the_best_candidate_is_kept_even_beyond_the_budget():
    # Real entries cost about 33 s at most (300-character title and reason), so with a 1-minute minimum
    # this rule is a guard: it needs an artificially long candidate to be seen.
    candidates = [entry("too-long", 90), entry("short", 6)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["too-long"]  # Budget already used up.


def test_only_the_first_candidate_is_forced_in():
    candidates = [entry("short", 6), entry("too-long", 90)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["short"]


def test_order_is_kept():
    candidates = [entry(name, seconds) for name, seconds in [("a", 21), ("b", 51), ("c", 9), ("d", 51), ("e", 9)]]
    # "b" and "d" are skipped; the others keep the selection order (best score first, then oldest).
    assert names(select_entries(candidates, budget_minutes=1)) == ["a", "c", "e"]


def test_candidates_are_not_modified():
    candidates = [entry("a", 21), entry("b", 51), entry("c", 9)]
    before = list(candidates)
    select_entries(candidates, budget_minutes=1)
    assert candidates == before


def test_a_tuple_of_candidates_is_accepted():
    assert names(select_entries((entry("a", 9), entry("b", 9)), budget_minutes=1)) == ["a", "b"]


# --- Properties on a realistic mix ---

@pytest.fixture
def realistic() -> list[DigestCandidate]:
    """Twelve entries from 6 s to 33 s, the realistic range. A fixture, not a module constant: if `entry()`
    breaks, each test fails on its own instead of the whole file failing to load."""
    return [entry(f"e{i}", seconds) for i, seconds in enumerate([33, 21, 12, 6, 27, 15, 9, 30, 18, 6, 24, 12])]


@pytest.mark.parametrize("budget_minutes", [1, 2, 3, 5, 10])
def test_selection_never_exceeds_the_budget(realistic, budget_minutes):
    selected = select_entries(realistic, budget_minutes)
    assert sum(reading_seconds(candidate) for candidate in selected) <= budget_minutes * 60


@pytest.mark.parametrize(("smaller", "larger"), [(1, 2), (2, 5), (5, 10)])
def test_a_larger_budget_keeps_what_the_smaller_one_kept_before_its_first_skip(realistic, smaller, larger):
    small, large = names(select_entries(realistic, smaller)), names(select_entries(realistic, larger))
    all_names = names(realistic)
    first_skip = next((i for i, name in enumerate(all_names) if name not in small), len(all_names))
    assert large[:first_skip] == all_names[:first_skip]


def test_a_larger_budget_can_hold_fewer_but_better_ranked_entries():
    # Not a bug: best first. With 2 minutes, the two well-ranked 54 s entries fit and take the room of
    # three lower-ranked short ones. So "more time" means "more of the best", not "more entries".
    # The 54 s costs are artificial (a real entry costs about 33 s at most): with realistic costs, a
    # search found no such case with up to 8 candidates between 1 and 2 minutes, but it stays possible.
    candidates = [entry("a", 9), entry("b", 54), entry("c", 54), entry("d", 6), entry("e", 6), entry("f", 6)]
    assert names(select_entries(candidates, budget_minutes=1)) == ["a", "d", "e", "f"]
    assert names(select_entries(candidates, budget_minutes=2)) == ["a", "b", "c"]
