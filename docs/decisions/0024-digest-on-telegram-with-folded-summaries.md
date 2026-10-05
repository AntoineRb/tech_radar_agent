# 0024. Digest on Telegram, in HTML, with folded summaries: the reading cost counts only what is visible

- Status: Accepted
- Date: 2026-10-05
- Supersedes the reading-cost part of [ADR 0023](0023-digest-selection.md)

## Context

The digest must reach the reader where they actually look, be quick to scan on a phone, and stay safe: titles, reasons and summaries are untrusted text (from the sources or from the LLM). ADR 0023 costed an entry with its summary (about 25 s) and an entry without summary with its reason (about 5 to 12 s). Once the display was designed, that no longer matched what the reader sees.

## Decision

**Channel: Telegram**, through the official Bot API: one HTTPS `POST` with `httpx`, no new dependency, free, 4096 characters per message. The reader gets a phone notification, the digest does not get lost among emails, and the chat keeps a history. Rejected:

- **WhatsApp**: the official API (Meta's WhatsApp Business Platform) needs a business account and a dedicated number, allows free-form messages only within 24 hours of the reader's last message (a daily digest needs a template approved by Meta), and is paid per message. Unofficial routes break its terms and the rule "official APIs only".
- **Email** and **Discord**: possible later; email can end up in spam and needs SMTP credentials, Discord allows 2000 characters per message.

**Format: Telegram HTML** (`parse_mode=HTML`) rather than MarkdownV2. Only `<`, `>` and `&` need escaping, with the standard `html.escape`; MarkdownV2 needs 18 characters escaped by hand, and one miss makes Telegram reject the whole message. Every external text (title, source, reason, summary, tags) is escaped, and links come only from the database (`url`, `extra.discussion_url`), escaped in `href` too. Telegram accepts only a few tags (`<b>`, `<i>`, `<a>`, `<code>`, `<blockquote>`…), which also limits what any injected text could do.

**Display**:

- Two sections sorted by score: **articles with a summary**, then **articles without one** (title, score, reason, link).
- Interests are shown as **tags** on each entry, not as groups: an article can have several interests or none, and the best article must stay on top.
- Each entry shows its title, score, tags and **reason**; the **summary is folded** in an expandable quote (`<blockquote expandable>`). The reason tells whether the article matters; one tap unfolds the summary.

**Reading cost: only what is visible counts**, the title and the reason, for every entry. The folded summary is not counted: unfolding it is time the reader chose to spend. Every entry now costs about the same (about 12 s; at most about 33 s with a 300-character title and reason).

**Budget**: with this cost, 5 minutes holds about 25 entries, which already covers a normal day above the threshold (about 20 articles, from a 25-article sample). The reader's config goes from 10 to 5 minutes, the code default.

## Consequences

- The budget becomes the time to **scan** the digest. On a normal day it no longer limits anything: the score threshold does the filtering, and the budget caps busy days. Showing the reason of every article scored 8 or more leaves the choice to the reader, since a high score does not guarantee interest.
- The distinction "an entry without summary costs about five times less" from ADR 0023 disappears: both kinds cost the same.
- "A larger budget can hold fewer entries" becomes rare: with realistic costs, a search found no case with up to 8 candidates between 1 and 2 minutes. It stays possible in principle, and a test keeps documenting it.
- The real number of articles scored 8 or more per day must be checked during the first days, to see whether 5 minutes starts to cut.
- A digest longer than 4096 characters is split into several Telegram messages (delivery step).
