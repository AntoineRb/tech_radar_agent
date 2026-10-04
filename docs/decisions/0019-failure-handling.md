# 0019. Failure handling in the agent loop

- Status: Accepted (loop implementation in progress)
- Date: 2026-10-04

## Context

Out of 100 articles, failures do not all mean the same thing. Retrying a bad key 100 times wastes time and, on a paid API, money; giving up on the first rate limit wastes the run.

## Decision

Based on the error categories of `LlmClient` (ADR 0012):

| Category | Reaction |
|---|---|
| About one article (`LlmError`, `ScoreValidationError`, `SummaryValidationError`) | skip the article, go on. It is retried at the next run while it stays in the recency window |
| Temporary (`LlmTemporaryError`) | retry twice with a growing wait (about 2 s then 8 s, or the server's `Retry-After`), then stop scoring |
| Fatal (`LlmFatalError`) | stop scoring at once |

- **Guard**: 5 per-article failures in a row stop scoring too: something global is wrong (broken prompt, misbehaving model).
- **Nothing is lost**: the collection and every article already scored are saved before any stop.
- **Exit code 3**: scoring stopped although the collection succeeded, so the problem shows in CI.

## Consequences

- No retry counter is stored: the 3-day window bounds retries of a failing article to about three, one per daily run.
- The loop decides; `Scorer` and `Summarizer` never catch errors.
