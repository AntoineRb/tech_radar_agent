# 0028. --send-only: send the digest from the database, without collecting or scoring

- Status: Accepted
- Date: 2026-10-06

## Context

[ADR 0027](0027-digest-in-the-run-dry-run-and-preview.md) gave two ways to see a digest without sending it (`--dry-run`, `--preview`), and one way to send it: a full run, which collects and calls the LLM. Run locally, the LLM is a model that needs a lot of memory. The reader sometimes wants the digest of what is already scored, on Telegram, without starting the model.

## Decision

- **`--send-only`**: no collection, no LLM call. The digest is built from what the database already holds (same selection and rendering as a normal run), sent on Telegram, and the articles of each confirmed message are **marked as sent**, exactly like in a normal run.
- It needs the Telegram settings, and returns exit code `4` when the digest did not go out entirely, like a normal run.
- When nothing is left to send, it sends the report of an empty day, which says this run collected and scored nothing (0 and 0).
- `--dry-run`, `--preview` and `--send-only` cannot be combined.

## Consequences

- The four ways to run the agent cover its two axes, with or without the LLM, sent or written to a file:

  | | Sent on Telegram, marked | Written to `output/`, nothing marked |
  |---|---|---|
  | Collect and score (LLM) | normal run | `--dry-run` |
  | From the database only | `--send-only` | `--preview` |

- A `--send-only` after a `--dry-run` sends exactly what the dry run showed (the database has not changed in between).
