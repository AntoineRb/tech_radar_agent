# 0006. Pluggable, config-driven collectors

- Status: Accepted
- Date: 2026-09-28

## Context

The first sources are Hacker News, RSS and GitHub. However, the agent may later watch something other than tech news. Adding or configuring a source should not require changes to the pipeline.

## Decision

- Every source is a subclass of an abstract `Collector` with a single method: `collect() -> list[Article]`.
- A registry (`COLLECTOR_TYPES`) maps a config `type` to its class. `build_collector()` passes every other key of the config entry to the constructor as keyword arguments.
- Each collector instance has a `name`, stored in `Article.source`, so the same type can be used several times with different options.
- A collector raises if the whole source fails, and skips items that fail individually.
- HTTP goes through a shared `http_client()` (timeout, User-Agent). Hacker News stories are fetched in parallel with a thread pool.

## Consequences

- Adding a source means writing one class and adding one registry line.
- Bad configuration fails right away (`ValueError` / `TypeError`) instead of in the middle of a run.
- `Article.source` holds the instance name (for example `hn-best`), not always the type.
- The registry is a plain dict, with no automatic plugin discovery. That is enough for now.
