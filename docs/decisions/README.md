# Decision log

Each file records one architecture decision: its context, the choice made, and its consequences. These are lightweight [ADRs](https://adr.github.io/). A decision is never edited after the fact. If it changes, a new ADR supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-no-agent-framework.md) | Build the agent loop without a framework | Accepted |
| [0002](0002-article-as-dataclass.md) | Model `Article` as a standard library dataclass | Accepted |
| [0003](0003-dedup-by-normalized-url.md) | Deduplicate articles by normalized URL | Accepted |
| [0004](0004-source-specific-data-in-extra.md) | Keep source-specific data in an `extra` dict | Accepted |
| [0005](0005-sqlite-schema.md) | SQLite schema and type mapping | Accepted |
| [0006](0006-pluggable-collectors.md) | Pluggable, config-driven collectors | Accepted |
| [0007](0007-security-baseline.md) | Security baseline: trusted dependencies, verified sources, untrusted content | Accepted |
| [0008](0008-llm-via-openai-compatible-api.md) | One LLM client for local and remote models, configured by environment variables | Accepted |

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```
