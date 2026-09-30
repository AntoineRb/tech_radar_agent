# 0008. One LLM client for local and remote models, configured by environment variables

- Status: Accepted
- Date: 2026-09-30

## Context

The agent needs an LLM for scoring and summaries. Two use cases:

- **Local**: a small model such as Qwen running on the developer's Mac. It is free and private.
- **Remote**: an API, when the agent runs on a server or in GitHub Actions, where there is no GPU.

Switching between the two must not require code changes or add complexity.

## Decision

- Talk to the LLM through the **OpenAI chat completions format** (`POST {base_url}/chat/completions`). Ollama exposes it locally, and most API providers expose it too.
- Call it directly with `httpx`, which is already a dependency. There is no provider SDK: no new dependency, and every request and response is visible.
- Configure it with three environment variables, read by `llm.load_llm_settings()`:

  | Variable | Required | Example |
  |---|---|---|
  | `LLM_BASE_URL` | yes | `http://localhost:11434/v1` (Ollama), `https://api.<provider>/v1` |
  | `LLM_MODEL` | yes | `qwen3:4b` |
  | `LLM_API_KEY` | remote only | secret, never committed |

  The location of the model is described by these variables, rather than by a `mode` switch. A switch would still need a URL and a model name, and this way no `if local:` branch is needed in the code.
- Locally, the variables live in a git-ignored `.env`, loaded with `uv run --env-file .env`, a built-in uv option. `.env.example` documents them. In CI, they come from GitHub secrets.
- Security exception: plain `http` is allowed for the LLM **only** towards `localhost`, `127.0.0.1` or `::1`. Everything else requires HTTPS. Collectors are not affected, and stay HTTPS-only.

## Consequences

- Switching between local and remote, or between two models, means editing `.env`.
- Only features common to OpenAI-compatible servers can be used. Provider-specific features are out of reach without a dedicated client.
- Small local models are more likely to return invalid JSON. Output validation (see [security](../security.md)) is mandatory, and invalid output is rejected.
- The API key never appears in `repr()`, so it cannot leak through logs.
