# 0009. Scoring output: score, reason and interest ids from the profile

- Status: Accepted
- Date: 2026-10-04

## Context

The LLM scores each article against the interest profile. Its answer must be machine-checked (security rule: reject, never guess), useful for the digest, and reusable for the feedback and hot-topic features planned later.

Free-form tags were considered. They drift (`Python`, `python`, `Python programming`…) and cannot be validated, so they would have to be cleaned up before any statistics could use them.

## Decision

The scoring answer is a JSON object with exactly three fields:

| Field | Type | Validation | Used for |
|---|---|---|---|
| `score` | integer | 0 to 10, an integer (not `7.5`, not `"7"`) | threshold and ranking |
| `reason` | text | non-empty, truncated to ~300 characters | humans only: digest and debugging. Never parsed or used for decisions |
| `interests` | list of ids | every id exists in the profile; may be empty | grouping in the digest, later feedback statistics |

Interests in `config/interests.yaml` become a mapping `id: description` under each priority:

```yaml
interests:
  high:
    ai-agents: AI agents (architecture, tool use, memory, evaluation)
```

- The **id** is short and stable (`[a-z0-9]+(-[a-z0-9]+)*`). The LLM returns it and it is stored. Renaming it breaks the link with past articles.
- The **description** is what the LLM reads. It can be reworded freely.
- Priorities (`high`, `medium`, `low`) are context for the LLM. The code does not compute the score from them.

The summary is **not** part of the scoring answer. It is a second call, only for articles above the threshold.

`profile.language` (a plain language name, default `English`) sets the language of the text shown to the user. Prompt instructions stay in English.

## Consequences

- With a closed list of ids, the server can be asked to constrain the output (a JSON schema with an `enum` in `response_format`). Validation in our code stays mandatory, because not every server supports this.
- Removing an interest stops new articles from being tagged with it. Already scored articles keep their stored ids.
- Guard rails against complexity: no extra field without a current use, no cross-field consistency rules, a single validation function, and an interest list kept short (~10-15, checked by a test).
- The `articles` table needs columns for `reason` and `interests` (to add when results are stored).
