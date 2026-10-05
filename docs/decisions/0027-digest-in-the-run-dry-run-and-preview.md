# 0027. The digest in every run: --dry-run, --preview, and exit code 4

- Status: Accepted
- Date: 2026-10-05

## Context

Each run now ends with the digest: selection, rendering, sending on Telegram, marking what was sent. The reader needs a way to see a digest without sending it, both to rehearse a full run before deploying and to tune the layout quickly without the LLM. On GitHub Actions, the exit code is the only signal that something went wrong: a bot that silently stops writing could go unnoticed for days.

## Decision

- **Every run ends with the digest**, sent on Telegram, with the articles of each confirmed message marked as sent ([ADR 0026](0026-telegram-delivery.md)). A day with no candidate sends the one-line report when `digest.send_empty_report` is on.
- **The digest goes out even when scoring stopped**: articles scored before the stop, or on earlier days, still deserve it.
- **`--dry-run`**: everything except sending: collection, scoring with the LLM, selection, rendering. The digest is written to `output/digest-YYYY-MM-DD.html`; nothing is sent, nothing is marked, so it can be run again and again. Collecting and scoring still update the database: that is the agent's normal memory, not an effect visible outside.
- **`--preview`**: the digest only, from what the database already holds: no collection, no LLM call, instant. Written to the same file, nothing sent or marked. For tuning the layout without the LLM's memory and time cost.
- Telegram settings are not required for `--dry-run` and `--preview`. The two options cannot be combined.
- **Exit code 4**: the digest was not sent, or only partly (Telegram settings missing or invalid, a fatal or lasting error, a refused message). Nothing is lost: unsent articles compete again for the next digest.
- When several problems happen, the earliest is reported: **1** (every source failed), then **3** (scoring skipped or stopped), then **4** (digest not sent).

## Consequences

- A broken bot, a revoked token or a blocked chat turns the scheduled run red, and GitHub sends an email.
- `--preview` reuses exactly the selection and rendering code of a real run: what it shows is what would be sent, except for Telegram folding the summaries.
- The empty-day report's best score covers recent articles not sent yet (the scoring window), not only those scored by this run.
