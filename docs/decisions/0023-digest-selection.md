# 0023. Digest selection: a reading-time budget, best first, oldest first on ties, never empty

- Status: Accepted
- Date: 2026-10-05

## Context

The digest is the agent's final decision: what deserves the reader's attention today. The volume of good articles varies a lot from one day to the next, and many well-scored articles (Hacker News links) have no summary because they have no text. The reader thinks in time ("5 minutes between two meetings"), not in a number of articles.

## Decision

- **Candidates**: articles scored at or above the threshold (`AGENT_SUMMARY_THRESHOLD`, 8), **not sent yet**, and within the same age window as scoring (`AGENT_MAX_ARTICLE_AGE_DAYS`, 3 days).
- **Articles without a summary are included**, shown differently (title, score, reason, link), so a good piece of news is never missed because it had no text. This keeps decision 5 of the summary design and [ADR 0021](0021-partial-failures-in-the-loop.md).
- **A reading-time budget instead of a number of articles**: `digest.reading_time_minutes` in `config/interests.yaml`, a whole number from 1 to 30, 5 by default ("a coffee"). It is the time to read the digest and decide what to open, not to read the articles. Each entry's cost is estimated from its **word count** (title plus summary or reason) and a reading speed, plus a small fixed cost per entry. One budget is shared by both kinds of entries: a link costs about five times less than a summary, so links cannot crowd summaries out.
- **Selection order**: best score first; on equal scores, the **oldest first**. An older article leaves the window sooner, so it gets its chance before newer ones that can still wait. Without this, an article could be pushed back every day until it expires (starvation).
- **An entry that does not fit is skipped, and selection goes on** with the next ones. A skipped article is not marked as sent: it competes again for the next digest. No carry-over mechanism is needed, the "sent" status does it.
- **Never empty while a candidate exists**: the best one is always included, even beyond the budget.
- **A day without candidates** sends a one-line activity report (articles collected, scored, best score) when `digest.send_empty_report` is true, the default. Silence would not tell a quiet day from a broken run, and the best score shows whether the threshold is too high.
- Reading speed and per-entry costs are constants in the code. Only the reader's preferences (budget, empty report) are in the config file ([ADR 0011](0011-settings-config-file-vs-environment.md)); the threshold stays in the environment because it depends on the model.

## Consequences

- One new column, `sent_at`, added in place like the scoring columns. `fetch_digest_candidates` returns the candidates already in selection order, and `mark_sent` marks a whole digest in one transaction, only once it was delivered.
- With a large budget (10 minutes during the first days), the budget rarely limits anything: the selection rules are then only visible in the tests, until the budget is lowered.
- An article can be skipped several days in a row and still expire if better ones keep coming; oldest-first on ties limits this, the age window bounds it.
