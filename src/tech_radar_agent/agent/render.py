"""Digest rendering in Telegram HTML (ADR 0024; labels: ADR 0025).

    render_digest(entries, labels, today)                             -> list[str]   the digest blocks
    render_empty_report(labels, threshold, collected, scored, best)   -> str         a day with no candidate

The output is a LIST OF BLOCKS (header, section titles, one block per entry), not one string: delivery
groups the blocks into messages of at most 4096 characters WITHOUT EVER cutting inside a tag, which
would make Telegram reject the whole message. So every block is complete HTML on its own.

One entry:

    🟢 9/10 · <a href="URL">Title</a>              badge, score, title linking to the article
    #python #dev_tooling · realpython            hashtags, source
    <i>Why: reason…</i>                          the reason, always visible
    <blockquote expandable>summary…</blockquote>  folded summary, only when there is one
    💬 <a href="HN URL">Discussion</a>           only when there is a discussion (Hacker News)

Security: EVERY text is escaped with html.escape(text, quote=True), including the labels (a translated
file is text nobody here wrote) and the URLs (they go inside href="..."). Links come only from the
database. Only Telegram's tags are used: <b>, <i>, <a href>, <blockquote expandable>.
"""

import html
import math
from collections.abc import Sequence
from datetime import date

from tech_radar_agent.agent.digest import reading_seconds
from tech_radar_agent.i18n import Labels
from tech_radar_agent.sanitize import is_safe_url
from tech_radar_agent.storage import DigestCandidate

TOP_SCORE = 9  # From this score the badge is green; below, yellow.
TOP_BADGE = "🟢"
GOOD_BADGE = "🟡"
HEADER_ICON = "🗞"
SECTION_ICONS = {"to_read": "📖", "also_worth_a_look": "🔗"}
DISCUSSION_ICON = "💬"


def _escape(text: str) -> str:
    """Make any text safe inside Telegram HTML, as content or as an attribute value."""
    return html.escape(text, quote=True)


# --- Building blocks ---


def score_badge(score: int) -> str:
    """The badge of a score: green from TOP_SCORE, yellow below (also under 8, if the threshold is lowered)."""
    return TOP_BADGE if score >= TOP_SCORE else GOOD_BADGE


def hashtag(interest_id: str) -> str:
    """An interest id as a clickable Telegram hashtag: "ai-agents" -> "#ai_agents".

    A dash ends a hashtag in Telegram, an underscore does not. Tapping it lists every past digest entry
    with the same tag: the chat history becomes searchable by topic. Ids are already checked by the
    config (lowercase letters, digits, dashes); the result is still escaped when displayed.
    """
    return "#" + interest_id.replace("-", "_")


def discussion_url(candidate: DigestCandidate) -> str | None:
    """The discussion link to show (Hacker News), or None.

    `extra` is not validated at collection time, so the value may be missing, not a string, or a
    dangerous link (javascript:...): only a safe web URL is kept. An "Ask HN" post has no external
    link, so its article URL already is the discussion: the same link is not shown twice.
    """
    url = candidate.article.extra.get("discussion_url")
    if not isinstance(url, str) or not is_safe_url(url) or url == candidate.article.url:
        return None
    return url


# --- One entry ---


def render_entry(candidate: DigestCandidate, labels: Labels) -> str:
    """One digest entry, as complete Telegram HTML (see the module docstring)."""
    article = candidate.article
    lines = [
        f"{score_badge(candidate.score)} {candidate.score}/10 · "
        f'<a href="{_escape(article.url)}">{_escape(article.title)}</a>'
    ]

    tags = " ".join(hashtag(interest) for interest in candidate.interests)
    lines.append(_escape(f"{tags} · {article.source}" if tags else article.source))

    lines.append(f"<i>{_escape(labels.text('why'))} {_escape(candidate.reason)}</i>")

    if candidate.summary:
        lines.append(f"<blockquote expandable>{_escape(candidate.summary)}</blockquote>")

    discussion = discussion_url(candidate)
    if discussion is not None:
        lines.append(f'{DISCUSSION_ICON} <a href="{_escape(discussion)}">{_escape(labels.text("discussion"))}</a>')

    return "\n".join(lines)  # Telegram has no <br>: real line breaks.


# --- The digest ---


def render_digest(entries: Sequence[DigestCandidate], labels: Labels, today: date) -> list[str]:
    """The digest blocks: the header, then each non-empty section with one block per entry.

    Args:
        entries: the result of select_entries, in selection order (best score first).
        labels: load_labels(config.profile.language).
        today: the digest date, passed in (never date.today() here) so tests do not depend on the clock.

    Returns:
        [header, section title, entry, entry, ..., section title, entry, ...]. Empty when there is no
        entry: a day with no candidate gets render_empty_report instead.
    """
    if not entries:
        return []

    # Rounded before ceil: a float sum like 120.00000000000001 s must not add a minute.
    minutes = max(1, math.ceil(round(sum(reading_seconds(entry) for entry in entries) / 60, 6)))
    count_key = "article_count_one" if len(entries) == 1 else "article_count_other"
    header = (
        f"<b>{HEADER_ICON} {_escape(labels.text('header', date=labels.date(today)))}</b>\n"
        f"{_escape(labels.text(count_key, count=len(entries), minutes=minutes))}"
    )
    blocks = [header]

    # Articles with a summary first, then the others; each section keeps the selection order.
    sections = {
        "to_read": [entry for entry in entries if entry.summary],
        "also_worth_a_look": [entry for entry in entries if not entry.summary],
    }
    for key, section in sections.items():
        if not section:
            continue  # An empty section gets no title.
        blocks.append(f"<b>{SECTION_ICONS[key]} {_escape(labels.text(key))}</b>")
        blocks.extend(render_entry(entry, labels) for entry in section)

    return blocks


def render_empty_report(labels: Labels, threshold: int, collected: int, scored: int, best: int | None) -> str:
    """The one-line report of a day with no candidate (option digest.send_empty_report).

    Proof that the agent ran, and a measure: days in a row with a best score just under the threshold
    hint that the threshold is too high for the model.
    """
    if best is None:
        text = labels.text("empty_report_nothing_scored", collected=collected)
    else:
        text = labels.text("empty_report", threshold=threshold, collected=collected, scored=scored, best=best)
    return _escape(text)
