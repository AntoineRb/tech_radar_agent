# 0018. Agent loop scope: one command, recent articles only, capped, threshold for summaries

- Status: Accepted
- Date: 2026-10-04

## Context

The agent must turn collected articles into scored, summarized ones every day, without scoring a month-old backlog or blowing up time and cost after a missed run.

## Decision

- **One command**: `uv run tech-radar-agent` collects, then scores and summarizes. If the LLM is not configured or fails, the run stops **after** the collection is saved. Separate steps (e.g. `--skip-collect`) may come later.
- **Only recent articles are scored**: unscored articles published (or collected, when there is no date) in the last `AGENT_MAX_ARTICLE_AGE_DAYS` days (3 by default, enough to absorb a missed daily run). Older ones keep `score = NULL` for good.
- **A cap per run**: at most `AGENT_MAX_ARTICLES_PER_RUN` articles (100), newest first.
- **Summaries above a threshold**: `AGENT_SUMMARY_THRESHOLD` (8). Measured on 25 articles: 8 keeps about a third (about twenty a day); 7 would keep more than half and stop filtering.

## Consequences

- A first run on an old database scores nothing until new articles are collected.
- The threshold must be retuned when changing models, since calibration differs.
- Old unscored rows accumulate: a purge may come later (keeping articles with reader feedback).
