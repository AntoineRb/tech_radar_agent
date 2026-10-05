"""Tests for agent/render.py: Telegram HTML, built from hand-made candidates and the real labels.

`TagCounter` (on the standard html.parser) checks that a block is complete HTML and uses only the tags
Telegram accepts: delivery splits the digest between blocks, so a tag left open in a block would make
Telegram reject a whole message.

Run one group only: uv run pytest tests/agent/test_render.py -k escape
"""

import html
from dataclasses import replace
from datetime import date
from html.parser import HTMLParser
from typing import Any

import pytest

from tech_radar_agent.agent.digest import ENTRY_OVERHEAD_SECONDS, READING_SPEED_WPM
from tech_radar_agent.agent.render import (
    GOOD_BADGE,
    MAX_MESSAGE_LENGTH,
    TOP_BADGE,
    Block,
    discussion_url,
    fit_entry,
    hashtag,
    render_digest,
    render_empty_report,
    render_entry,
    score_badge,
    telegram_length,
)
from tech_radar_agent.i18n import load_labels
from tech_radar_agent.models import Article
from tech_radar_agent.storage import DigestCandidate

EN = load_labels("English")
FR = load_labels("French")
TODAY = date(2026, 10, 6)  # A Tuesday.
HN = "https://news.ycombinator.com/item?id=42"
TELEGRAM_TAGS = {"b", "i", "a", "blockquote"}  # The tags this module may produce.


def make_candidate(
    title: str = "Faster JSON parsing",
    url: str = "https://example.com/article",
    *,
    score: int = 9,
    reason: str = "Relevant for a Python developer.",
    summary: str | None = None,
    interests: tuple[str, ...] = (),
    source: str = "realpython",
    extra: dict[str, Any] | None = None,
) -> DigestCandidate:
    article = Article(source=source, title=title, url=url, extra=extra or {})
    return DigestCandidate(id=1, article=article, score=score, reason=reason, interests=interests, summary=summary)


class TagCounter(HTMLParser):
    """Records the tags of an HTML fragment and whether every opened tag is closed."""

    def __init__(self, fragment: str) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[str] = []
        self.open: list[str] = []
        self.feed(fragment)
        self.close()

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.open.append(tag)

    def handle_endtag(self, tag: str) -> None:
        assert self.open and self.open[-1] == tag, f"</{tag}> does not close the last opened tag {self.open}"
        self.open.pop()


def assert_complete_telegram_html(fragment: str) -> list[str]:
    counter = TagCounter(fragment)
    assert counter.open == [], f"tags left open: {counter.open}"
    assert set(counter.tags) <= TELEGRAM_TAGS, f"unexpected tags: {set(counter.tags) - TELEGRAM_TAGS}"
    return counter.tags


# --- Building blocks ---


@pytest.mark.parametrize(("score", "badge"), [(10, TOP_BADGE), (9, TOP_BADGE), (8, GOOD_BADGE), (6, GOOD_BADGE)])
def test_score_badge(score, badge):
    assert score_badge(score) == badge


@pytest.mark.parametrize(("interest", "tag"), [("ai-agents", "#ai_agents"), ("python", "#python"), ("a-b-c", "#a_b_c")])
def test_hashtag_replaces_dashes(interest, tag):
    assert hashtag(interest) == tag


def test_discussion_url_is_returned_when_safe():
    assert discussion_url(make_candidate(extra={"discussion_url": HN})) == HN


@pytest.mark.parametrize(
    "extra",
    [
        {},
        {"discussion_url": None},
        {"discussion_url": 42},
        {"discussion_url": ["https://news.ycombinator.com"]},
        {"discussion_url": "javascript:alert(1)"},
        {"discussion_url": "data:text/html,<script>x</script>"},
        {"discussion_url": "file:///etc/passwd"},
        {"discussion_url": ""},
    ],
    ids=["missing", "none", "number", "list", "javascript", "data", "file", "empty"],
)
def test_discussion_url_is_ignored_when_missing_or_unsafe(extra):
    assert discussion_url(make_candidate(extra=extra)) is None


def test_discussion_url_is_not_repeated_for_ask_hn():
    # An "Ask HN" post has no external link: its article URL already is the discussion.
    assert discussion_url(make_candidate(url=HN, extra={"discussion_url": HN})) is None


# --- One entry ---


def test_entry_shows_badge_score_and_linked_title():
    first_line = render_entry(make_candidate(score=9), EN).splitlines()[0]
    assert first_line == f'{TOP_BADGE} 9/10 · <a href="https://example.com/article">Faster JSON parsing</a>'


def test_entry_shows_hashtags_and_source():
    entry = render_entry(make_candidate(interests=("ai-agents", "python"), source="hackernews"), EN)
    assert entry.splitlines()[1] == "#ai_agents #python · hackernews"


def test_entry_without_interests_shows_only_the_source():
    assert render_entry(make_candidate(interests=()), EN).splitlines()[1] == "realpython"


def test_entry_shows_the_reason_with_the_why_label():
    candidate = make_candidate(reason="Useful.")
    assert "<i>Why: Useful.</i>" in render_entry(candidate, EN)
    assert "<i>Pourquoi : Useful.</i>" in render_entry(candidate, FR)


def test_entry_folds_the_summary():
    folded = render_entry(make_candidate(summary="What it brings."), EN)
    assert "<blockquote expandable>What it brings.</blockquote>" in folded
    assert "blockquote" not in render_entry(make_candidate(summary=None), EN)


def test_entry_shows_the_discussion_link_only_when_there_is_one():
    with_link = render_entry(make_candidate(extra={"discussion_url": HN}), EN)
    assert f'💬 <a href="{HN}">Discussion</a>' in with_link
    assert "💬" not in render_entry(make_candidate(), EN)


HOSTILE = [
    "<script>alert(1)</script>",
    "</blockquote><b>injected</b>",
    "</i></a><a href='javascript:alert(1)'>click</a>",
    "Q&A <3 && x < y",
]


@pytest.mark.parametrize("text", HOSTILE)
@pytest.mark.parametrize("field", ["title", "reason", "summary", "source"])
def test_entry_escapes_every_external_text(field, text):
    entry = render_entry(make_candidate(**{field: text}), EN)
    tags = assert_complete_telegram_html(entry)  # Nothing injected is read as a tag...
    assert "script" not in tags
    assert TagCounter(entry).tags.count("a") == 1  # ...and the only link is the article's.
    # The text is still there, as text: unescaping the entry gives it back.
    assert text in html.unescape(entry)


def test_entry_escapes_quotes_in_urls():
    # A quote in a URL must not close href="..." and open another attribute.
    entry = render_entry(make_candidate(url='https://example.com/a"onmouseover="alert(1)'), EN)
    assert 'href="https://example.com/a&quot;onmouseover=&quot;alert(1)"' in entry
    assert "onmouseover=\"" not in entry


def test_entry_escapes_the_discussion_url():
    entry = render_entry(make_candidate(extra={"discussion_url": 'https://news.ycombinator.com/item?id=1&x="y"'}), EN)
    assert 'href="https://news.ycombinator.com/item?id=1&amp;x=&quot;y&quot;"' in entry


def test_entry_is_complete_html_with_telegram_tags_only():
    candidate = make_candidate(summary="What it brings.", interests=("python",), extra={"discussion_url": HN})
    assert sorted(assert_complete_telegram_html(render_entry(candidate, EN))) == ["a", "a", "blockquote", "i"]


# --- The digest ---


def digest_html(entries, labels, today) -> list[str]:
    """The HTML of each block of render_digest."""
    return [block.html for block in render_digest(entries, labels, today)]


def costing(seconds: float, name: str, **fields: Any) -> DigestCandidate:
    """A candidate whose reading cost is exactly `seconds` (a one-word title plus a reason)."""
    reason_words = round((seconds - ENTRY_OVERHEAD_SECONDS) * READING_SPEED_WPM / 60) - 1
    return make_candidate(title=name, url=f"https://example.com/{name}", reason="word " * reason_words, **fields)


def test_empty_digest_has_no_block():
    assert render_digest([], EN, TODAY) == []


def test_digest_starts_with_the_header():
    header = digest_html([make_candidate()], EN, TODAY)[0]
    title, count = header.splitlines()
    assert title == "<b>🗞 Tech Radar · Tuesday 6 October</b>"
    assert count.startswith("1 article · about ")


def test_header_uses_singular_and_plural():
    assert digest_html([make_candidate()], EN, TODAY)[0].splitlines()[1].startswith("1 article ")
    three = [make_candidate(title=f"T{i}", url=f"https://example.com/{i}") for i in range(3)]
    assert digest_html(three, EN, TODAY)[0].splitlines()[1].startswith("3 articles ")


@pytest.mark.parametrize(
    ("costs", "minutes"),
    [([63], 2), ([12], 1), ([60, 60], 2), ([30, 33], 2), ([6], 1)],
    ids=["63s", "12s", "exactly-120s", "63s-in-two", "6s"],
)
def test_header_minutes_are_rounded_up_and_at_least_one(costs, minutes):
    entries = [costing(seconds, f"e{i}") for i, seconds in enumerate(costs)]
    assert f"about {minutes} min to scan" in digest_html(entries, EN, TODAY)[0]


def test_entries_with_summary_come_first_then_the_others():
    no_summary = make_candidate(title="Link only", url="https://example.com/1", score=10)
    with_summary = make_candidate(title="Summarized", url="https://example.com/2", score=8, summary="S.")
    blocks = digest_html([no_summary, with_summary], EN, TODAY)
    assert blocks[1] == "<b>📖 TO READ</b>"
    assert "Summarized" in blocks[2]
    assert blocks[3] == "<b>🔗 ALSO WORTH A LOOK</b>"
    assert "Link only" in blocks[4]
    assert len(blocks) == 5


def test_order_is_kept_within_each_section():
    entries = [make_candidate(title=name, url=f"https://example.com/{name}", summary=summary)
               for name, summary in [("a", "S"), ("b", None), ("c", "S"), ("d", None), ("e", "S")]]
    entry_blocks = [block for block in digest_html(entries, EN, TODAY) if "/10 · " in block]
    titles = [block.splitlines()[0].split('">', 1)[1].removesuffix("</a>") for block in entry_blocks]
    assert titles == ["a", "c", "e", "b", "d"]


def test_empty_section_has_no_title():
    blocks = digest_html([make_candidate(summary="S.")], EN, TODAY)
    assert "<b>📖 TO READ</b>" in blocks
    assert not [block for block in blocks if "ALSO WORTH A LOOK" in block]


def test_digest_in_french():
    blocks = digest_html([make_candidate(summary="S."), make_candidate(url="https://example.com/2")], FR, TODAY)
    assert blocks[0].splitlines()[0] == "<b>🗞 Tech Radar · mardi 6 octobre</b>"
    assert "environ" in blocks[0] and "min de lecture" in blocks[0]
    assert "<b>📖 À LIRE</b>" in blocks and "<b>🔗 À VOIR AUSSI</b>" in blocks


def test_every_block_is_complete_html_and_fits_in_a_telegram_message():
    # Realistic maximum sizes: 300-character title and reason, 600-character summary, long URLs.
    big = dict(reason="r" * 300, summary="s" * 600, interests=("ai-agents", "python", "llm"),
               extra={"discussion_url": HN + "0" * 50})
    entries = [make_candidate(title="T" * 300, url=f"https://example.com/{i}?" + "q=1&" * 60, **big) for i in range(5)]
    entries += [make_candidate(title="<b>Link</b>", url="https://example.com/link")]
    for block in digest_html(entries, FR, TODAY):
        assert_complete_telegram_html(block)
        assert len(block) < 4096


# --- Report of a day with no candidate ---


def test_empty_report_with_a_best_score():
    assert render_empty_report(EN, threshold=8, collected=42, scored=38, best=7) == (
        "Nothing scored 8 or more today: 42 new articles, 38 scored, best score 7."
    )


def test_empty_report_when_nothing_was_scored():
    assert render_empty_report(EN, threshold=8, collected=12, scored=0, best=None) == (
        "Nothing scored today: 12 new articles collected."
    )


def test_empty_report_in_french_is_escaped():
    report = render_empty_report(FR, threshold=8, collected=42, scored=38, best=7)
    assert report.startswith("Rien de noté 8 ou plus aujourd&#x27;hui")  # The apostrophe is escaped.
    assert_complete_telegram_html(report)



# --- Blocks carry article ids ---


def test_entry_blocks_carry_their_article_id_and_others_none():
    with_summary = replace(make_candidate(title="A", url="https://example.com/a", summary="S."), id=11)
    no_summary = replace(make_candidate(title="B", url="https://example.com/b"), id=22)
    blocks = render_digest([with_summary, no_summary], EN, TODAY)
    assert all(isinstance(block, Block) for block in blocks)
    assert [block.article_id for block in blocks] == [None, None, 11, None, 22]  # header, title, A, title, B


# --- Entries too long for one Telegram message ---


def test_telegram_length_counts_emojis_twice():
    assert telegram_length("abc") == 3
    assert telegram_length("🟢") == 2  # Outside the basic plane: two UTF-16 code units.
    assert telegram_length("é") == 1


def huge_url(length: int) -> str:
    return "https://example.com/?" + "q" * (length - len("https://example.com/?"))


def test_a_normal_entry_keeps_everything():
    candidate = make_candidate(summary="S.", extra={"discussion_url": HN})
    assert fit_entry(candidate, EN) == render_entry(candidate, EN)


def test_a_too_long_entry_drops_its_summary_first():
    # The summary alone pushes it over the limit: the lighter version keeps the discussion link.
    candidate = make_candidate(summary="s " * 2100, extra={"discussion_url": HN})
    fitted = fit_entry(candidate, EN)
    assert fitted is not None and "blockquote" not in fitted and "Discussion" in fitted
    assert telegram_length(fitted) <= MAX_MESSAGE_LENGTH


def test_a_still_too_long_entry_drops_its_discussion_link_too():
    # A long URL (escaped twice: article and discussion) leaves room only without the discussion link.
    long_url = huge_url(2100)
    discussion = long_url.replace("example.com", "news.example.com")
    candidate = make_candidate(url=long_url, summary="S.", extra={"discussion_url": discussion})
    fitted = fit_entry(candidate, EN)
    assert fitted is not None and "Discussion" not in fitted and "blockquote" not in fitted
    assert long_url in fitted  # The title still links to the article.


def test_an_entry_that_cannot_fit_is_left_out_and_logged(caplog):
    too_long = make_candidate(title="Too long", url=huge_url(4200))
    normal = make_candidate(title="Normal", url="https://example.com/normal")
    assert fit_entry(too_long, EN) is None
    with caplog.at_level("WARNING"):
        blocks = digest_html([too_long, normal], EN, TODAY)
    assert "1 article · " in blocks[0]  # The header counts what is shown.
    assert not [block for block in blocks if "Too long" in block]
    assert "left out" in caplog.text and "Too long" in caplog.text


def test_nothing_shown_when_no_entry_fits():
    assert render_digest([make_candidate(url=huge_url(4200))], EN, TODAY) == []
