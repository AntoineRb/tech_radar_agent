# Configuration

Configuration comes from two places:

- [`config/interests.yaml`](../config/interests.yaml), committed: **what** you care about and where articles come from.
- Environment variables, never committed: **where** things run (which LLM) and secrets. See [Environment variables](#environment-variables).

## `config/interests.yaml`

Everything the agent needs to know about you lives in [`config/interests.yaml`](../config/interests.yaml). The file has two sections: the interest profile, used by the LLM to score articles, and the list of sources. It is loaded by `config.load_config()` with `yaml.safe_load` (see [security](security.md)).

### `profile`: what you care about

```yaml
profile:
  about: >
    A few sentences about who you are and what you look for.
  interests:
    high:
      - AI agents (architecture, tool use, memory, evaluation)
    medium:
      - Apple (platforms, developer tools, hardware)
    low:
      - Open source projects gaining traction
  not_interested:
    - Crypto and blockchain
```

| Key | Meaning |
|---|---|
| `about` | Free text that gives the LLM some context. `>` joins the lines into one paragraph |
| `interests.high` / `medium` / `low` | Topics by priority. The scoring prompt can weigh them differently |
| `not_interested` | Topics that should lower the score, even if they match an interest |

Tips:

- Topics are free text. The LLM matches meaning rather than keywords.
- Be specific. "Apple (platforms, developer tools, hardware)" gives better results than "Apple", which would also match earnings and rumors.
- The exclusion list matters as much as the interests: it is what keeps the digest short.

### `sources`: where articles come from

A list of entries. `type` picks the collector, and every other key is one of its options. See [collectors](architecture/collectors.md) for the options of each type.

```yaml
sources:
  - type: hackernews
    feed: top
    limit: 40
    min_points: 30
  - type: rss
    name: simon-willison
    url: https://simonwillison.net/atom/everything/
    limit: 10
```

Rules:

- Each source needs a unique `name`. The name defaults to the type, so it is required as soon as a type is used twice.
- Only official APIs and feeds published by the publisher itself, over HTTPS. Check a new feed before adding it (it responds, has recent posts, and is served from the publisher's domain), and note the check date in the file.
- `limit` controls the volume of each source. Keep it low for noisy feeds such as arXiv.

### Validation

The whole configuration is checked **before any network call**. The run stops with exit code `2` in these cases:

- the file is missing or is not valid YAML;
- a YAML tag tries to build a Python object;
- `sources` is missing or empty;
- a source has an unknown `type` or a misspelled option;
- two sources have the same name.

## Environment variables

Settings that depend on where the agent runs, and secrets. Locally, they go in a `.env` file at the repository root. The file is git-ignored, and you create it by copying [`.env.example`](../.env.example):

```bash
cp .env.example .env
uv run --env-file .env tech-radar-agent
```

In CI (GitHub Actions), they come from the repository secrets.

| Variable | Required | Meaning |
|---|---|---|
| `LLM_BASE_URL` | yes | Base URL of a server that speaks the OpenAI chat completions format. HTTPS, or `http://localhost…` for a local model |
| `LLM_MODEL` | yes | Model name as the server knows it, e.g. `qwen3:4b` in Ollama |
| `LLM_API_KEY` | remote APIs | Secret key. Leave it empty for a local model |
| `LLM_REASONING_EFFORT` | no | Sent as `reasoning_effort` in every request. `none` turns off a model's thinking phase (qwen3.6 in Ollama: ~0.3 s instead of ~18 s per call). Leave it empty if the server rejects the field |
| `LLM_REQUEST_TIMEOUT` | no | Seconds for one LLM call, default `30`. A local model's first call loads it into memory (~20 s) |
| `GITHUB_TOKEN` | no | Higher GitHub search rate limit. Set automatically in GitHub Actions |

They are read by `llm.load_llm_settings()`, which raises `ValueError` if a required variable is missing, if the URL is not allowed, or if the timeout is not a positive number. See [ADR 0008](decisions/0008-llm-via-openai-compatible-api.md).

### Local model with Ollama

1. Install [Ollama](https://ollama.com) and pull a model from its library (the exact tag is shown on the model's page), for example `ollama pull qwen3:4b`.
2. Ollama serves it on `http://localhost:11434`, and its OpenAI-compatible API lives under `/v1`.
3. In `.env`, set `LLM_BASE_URL=http://localhost:11434/v1` and `LLM_MODEL=<the tag>`, and leave `LLM_API_KEY` empty.

Smaller models are faster but judge less reliably and return invalid JSON more often. Try a few, since switching is a one-line change in `.env`.

### Remote API

Set the provider's OpenAI-compatible base URL (HTTPS), the model name and the API key. Check the provider's documentation to confirm it supports the OpenAI chat completions format.
