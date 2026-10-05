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
| [0009](0009-scoring-output-and-interest-ids.md) | Scoring output: score, reason and interest ids from the profile | Accepted |
| [0010](0010-testing-without-network-or-llm.md) | Tests run without network or LLM, and attack the code with hostile input | Accepted |
| [0011](0011-settings-config-file-vs-environment.md) | Preferences in the config file, deployment settings in the environment | Accepted |
| [0012](0012-llm-client-contract.md) | LLM client contract: no tools, strict answers, three error categories | Accepted |
| [0013](0013-trusted-system-untrusted-user-message.md) | Trusted instructions in the system message, the untrusted article alone in the user message | Accepted |
| [0014](0014-scoring-input-and-call-settings.md) | Scoring input and call settings | Accepted |
| [0015](0015-prompts-changed-on-measured-evidence.md) | Prompt changes are decided on measurements against a real model | Accepted |
| [0016](0016-reader-language.md) | Instructions in English, reader-facing text in the reader's language | Accepted |
| [0017](0017-summary-what-the-article-brings.md) | Summary: what the article brings, or nothing | Accepted |
| [0018](0018-agent-loop-scope.md) | Agent loop scope: one command, recent articles only, capped, threshold for summaries | Accepted |
| [0019](0019-failure-handling.md) | Failure handling in the agent loop | Accepted |
| [0020](0020-storing-results.md) | Storing results: four new columns, the model recorded, in-place schema upgrade | Accepted |
| [0021](0021-partial-failures-in-the-loop.md) | Partial failures in the loop: a failed summary keeps the score, a stop saves nothing | Accepted |
| [0022](0022-continuous-integration.md) | Continuous integration: tests on every pull request and push, with pinned actions and a read-only token | Accepted |
| [0023](0023-digest-selection.md) | Digest selection: a reading-time budget, best first, oldest first on ties, never empty | Accepted |

## Template

```markdown
# NNNN. Title

- Status: Proposed | Accepted | Superseded by NNNN
- Date: YYYY-MM-DD

## Context
## Decision
## Consequences
```
