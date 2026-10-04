# 0012. LLM client contract: no tools, strict answers, three error categories

- Status: Accepted
- Date: 2026-10-04

## Context

`LlmClient` is the only place that talks to the LLM. Callers (scoring, summary, the loop) need to rely on what it returns, and to react differently to a bad answer, a busy server or a broken setup.

## Decision

- **No tools, enforced by code**: `chat()` refuses `tools`, `tool_choice`, `functions` and related options (`TypeError`, nothing is sent), and rejects any answer containing a tool call. The LLM can only return text, which the program treats as data.
- **Strict answers**: a non-2xx status, invalid JSON, a missing field, `content` that is not text, a cut-off answer (`finish_reason == "length"`), an unclosed `<think>` block or an empty answer all raise. `<think>…</think>` blocks are removed. The returned text is never empty.
- **No redirects followed**: a redirect could send prompts elsewhere, or downgrade HTTPS.
- **Options set to `None` are not sent**, so a caller can drop a default for one call.
- **Three error categories**, all subclasses of `LlmError`:

  | Class | Raised for | Expected reaction |
  |---|---|---|
  | `LlmError` | a problem with this call (bad answer, other statuses) | skip this item |
  | `LlmTemporaryError` | 429, 500, 502-504, timeouts, lost connection; carries `retry_after` | wait, retry |
  | `LlmFatalError` | 400, 401, 403, 404, redirects, connection refused or unknown host | stop |

- The API key only lives in the request header: never in an attribute, a log or an error message. Error details from the server are cleaned and truncated.

## Consequences

- `except LlmError` catches everything; callers that care can tell the categories apart without parsing messages.
- Checked against Ollama: an unknown model and a stopped server are both fatal.
- `500` is classed as temporary: Ollama returns it when a model fails to load, which is worth one retry.
