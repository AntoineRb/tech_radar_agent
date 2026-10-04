# 0017. Summary: what the article brings, or nothing

- Status: Accepted
- Date: 2026-10-04

## Context

Articles above the threshold get a summary in the digest. The scoring already explains why an article matters (`reason`). A summary is shown to a human and written from untrusted content, so it must neither invent nor carry anything harmful.

## Decision

- **Role**: `summary` says **what the article concretely brings** (what it shows, measures, builds or proposes, and its stated result), in 2-3 sentences, 80 words at most. It never explains relevance: that is `reason`.
- **Input**: all the stored content (3,000 characters), through the same hardened user message as scoring. Only the profile's **language** is used, so the summary is not steered towards the reader's interests.
- **No summary rather than an invented one**: below 300 characters of content, no LLM call at all; if the model finds nothing reliable to summarize, it answers `{"summary": ""}`. Both give `None`, which is not an error (nothing is retried).
- **Technical level**: match the article's level and vocabulary; keep technical terms, names and numbers as written.
- **Strict answer**: exactly the key `summary`, no duplicate keys. The whole answer is rejected if it contains anything clickable or executable: URLs, `javascript:`/`data:` schemes, Markdown links, HTML tags (matched by name), event handler attributes. The check runs after cleaning (an invisible character cannot hide a link) and before truncation (a link past the limit still counts).
- **No exception to the injection rule**, even for articles that quote messages: loosening it could open a breach.

## Consequences

- Technical text with generics and comparisons (`Vec<T>`, `p99 < 5 ms`) is accepted; an unknown HTML tag gets through. This filter is a second barrier: the digest will escape all LLM text.
- Some short posts that quote a message get no summary (checked: caused by the faithfulness rule, not by the injection rule). Accepted: a missing summary is better than an invented one.
