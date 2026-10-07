# 0029. Pacing the LLM requests: LLM_MIN_INTERVAL_SECONDS

- Status: Accepted
- Date: 2026-10-07

## Context

The daily run will go to GitHub Actions, where the local model cannot run: it needs a remote LLM API. Free tiers limit the number of requests per minute (RPM) and per day (RPD). On Google AI Studio's free tier, Gemini 3.8 Flash and 2.5 Flash-Lite allow 5 to 10 requests per minute and 20 per day; Gemini 3.1 Flash-Lite, the model we kept, allows 15 per minute and 500 per day.

A run sends its requests back to back: one per article scored, one more per summary. The retries of [ADR 0019](0019-failure-handling.md) (2 s, then 8 s) cannot outlast a per-minute limit: a run over the limit would fail every request until it stops.

## Decision

- **`LLM_MIN_INTERVAL_SECONDS`**: the minimum number of seconds between the starts of two LLM requests. Optional, **0 by default** (no wait: a local model is unchanged). A number from 0 to **300** included; anything else (text, negative, `nan`, `inf`, above 300) is refused when the settings are read, and scoring is skipped (exit code 3). The upper bound catches a typo such as milliseconds (`6000` would wait 100 minutes per request).
- **In `LlmClient.chat()`**, right before the request is sent, not in the agent loop. Every request goes through there: scoring, summaries, retries, and any later caller (an evaluation set). The quota belongs to the provider, like the other `LLM_*` settings, not to the agent logic.
- **Measured from start to start**, with a monotonic clock: a request that took 4 s with a 6 s interval is followed after 2 s, one that took longer is followed at once. This is how a provider counts requests per minute, and no time is lost.
- **Every sent request counts**, a failed one too (the server may have counted it, and the retry that follows must be spaced). A request refused by the client before sending (a forbidden option) does not.
- The clock and the wait are parameters of `LlmClient` (`clock=time.monotonic`, `sleep=time.sleep`): tests use a fake clock and never wait.

## Consequences

- Setting it: `60 / requests per minute`, plus a margin (10 RPM → 7 s).
- It does **not** help with a daily quota: spacing the requests does not reduce their number. A daily quota needs a lower `AGENT_MAX_ARTICLES_PER_RUN`, a paid tier, or another provider.
- A run gets slower: with 7 s, 15 requests take at least 1 min 38 s. Nothing to gain from it on a local model, where it stays at 0.
- The loop's retry waits (2 s, 8 s, or `Retry-After`) count as time passed: after them, the client only waits what is left of the interval, if anything.
