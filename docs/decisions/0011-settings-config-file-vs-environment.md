# 0011. Preferences in the config file, deployment settings in the environment

- Status: Accepted
- Date: 2026-10-04

## Context

Settings were starting to pile up: interest profile, sources, LLM location, timeouts, scoring window, summary threshold. Each one needed a home, and the same question kept coming back: YAML file or environment variable?

## Decision

One criterion: **does the value change with where the agent runs?**

- **No** → `config/interests.yaml`, committed: what the reader cares about (`profile`, including `language`) and where articles come from (`sources`).
- **Yes** → environment variables, never committed (`.env` locally, GitHub secrets in CI), documented in `.env.example`:
  - `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (ADR 0008);
  - `LLM_REASONING_EFFORT` (a field some servers reject), `LLM_REQUEST_TIMEOUT` (default 30 s);
  - `AGENT_MAX_ARTICLE_AGE_DAYS` (3), `AGENT_MAX_ARTICLES_PER_RUN` (100), `AGENT_SUMMARY_THRESHOLD` (8). The threshold lives here because scores depend on the model, which is itself set in the environment.
- Secrets only ever come from the environment.
- Every setting is validated when loaded, with a clear message, before any network call. Optional ones have defaults.

## Consequences

- Switching from a local model to an API, or retuning for a new model, is a `.env` change, with no code change.
- `.env` is loaded with `uv run --env-file .env`: no extra dependency.
- A test checks that `.env.example` documents the agent defaults.
