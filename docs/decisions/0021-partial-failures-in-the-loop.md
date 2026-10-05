# 0021. Partial failures in the loop: a failed summary keeps the score, a stop saves nothing

- Status: Accepted
- Date: 2026-10-05

## Context

An article at or above the threshold needs two LLM calls: a score, then a summary. The summary can fail after the score succeeded. `fetch_articles_to_score` only returns unscored articles, so once a score is saved, the article is never summarized again.

The summary can fail in two very different ways:

- the answer is invalid (a link, HTML, bad JSON). Calls run at temperature 0, so the same input gives the same answer: retrying would fail again;
- the server is down (fatal error, or a temporary error that outlasts the retries). That does pass: a retry later is likely to work.

## Decision

Retry only when a new attempt **can** give something else.

- **Invalid summary: keep the score, without a summary** (option A). The article still helps in the digest (title, score, reason, link), like an article too short to be summarized.
- **Stop during the summary: save nothing for that article** (option D). It stays unscored, and `fetch_articles_to_score` picks it up again, from scratch, at the next run. So at or above the threshold, `save_score` runs **after** the summary attempt; below it, right after the score.
- **Only scoring failures count towards `MAX_CONSECUTIVE_FAILURES`.** A summary failure only increments `summary_failed`.
- **The run report** splits the articles into `scored`, `score_failed` and `remaining` (each article in exactly one), with `summarized` and `summary_failed` as a breakdown of `scored`.
- **Exit codes**: `3` when scoring is skipped (invalid LLM or agent settings) or stopped early; `1` (every source failed) is reported first when both happen.

Rejected:

- **B, retry the summary at once**: useless at temperature 0.
- **C, a query that retries missing summaries at later runs**: it needs a new column or a sentinel value to tell "nothing to summarize" from "failed", for data that is not critical.

## Consequences

- No new column, query or retry counter: the existing "unscored" query doubles as the recovery mechanism.
- After an outage during a summary, one score is computed twice.
- A summary rejected once is lost for good. Option C stays possible if missing summaries show in real digests.
- A broken summary prompt does not stop the run; it shows in `summary_failed` and in the warnings. A separate counter would be simple to add.
