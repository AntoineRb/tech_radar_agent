# 0007. Security baseline: trusted dependencies, verified sources, untrusted content

- Status: Accepted
- Date: 2026-09-28

## Context

The agent pulls text written by strangers, passes it to an LLM, and shows the result to a human. It will also run unattended in CI with secrets. This creates three risks:

- a compromised dependency (supply chain);
- a fake or hijacked source;
- prompt injection hidden in an article, which could manipulate the scores or the summaries.

## Decision

Adopt the rules in [security.md](../security.md) as project requirements:

1. **Dependencies**: prefer the standard library. Vet each package before adding it, install only from PyPI through `uv`, commit the hash-pinned `uv.lock`, run `pip-audit` before merging dependency changes, and pin GitHub Actions to a commit SHA.
2. **Sources**: use only official APIs and publisher feeds, over HTTPS, with a timeout and a size limit. Collected URLs are data: only `http`/`https`, never fetched automatically. Keep secrets in the environment only. Load YAML with `yaml.safe_load`.
3. **Content**: all collected content is untrusted data. Sanitize it at parsing time, delimit it in prompts, validate the LLM output against a strict schema, give the LLM no tools, and escape its output in the digest.

## Consequences

- Every new dependency or source needs a short review first.
- Some sanitization runs on every article (a small CPU cost), and truncation limits what the LLM sees.
- Prompt injection cannot be fully prevented, only contained. The worst case is a wrong score or summary for one article, never an action.
