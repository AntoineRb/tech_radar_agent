# 0026. Telegram delivery: whole blocks per message, marked message by message, the token never leaks

- Status: Accepted
- Date: 2026-10-05

## Context

The digest goes to the reader's Telegram chat through the official Bot API ([ADR 0024](0024-digest-on-telegram-with-folded-summaries.md)). A message holds at most 4096 characters, so a busy digest needs several messages, and any of them can fail. The bot token gives full control of the bot and is part of every API URL (`https://api.telegram.org/bot<TOKEN>/sendMessage`). The agent will run on GitHub Actions, where run logs may be public.

## Decision

- **Settings from the environment** (deployment settings, [ADR 0011](0011-settings-config-file-vs-environment.md)): `TELEGRAM_BOT_TOKEN` (format checked) and `TELEGRAM_CHAT_ID`, which must be **positive**: a private chat, never a group or a channel.
- **Whole blocks per message.** The rendering returns complete HTML blocks, each entry carrying its article id. They are packed into as few messages as possible, never cut, with the length measured as Telegram does (UTF-16 code units, an emoji counts 2). An entry too long for one message is lightened at rendering (without its summary, then without its discussion link), or left out and logged; no HTML is ever cut.
- **Marked message by message.** Once Telegram confirms a message, its articles are marked as sent, and nothing is marked before. Delivery never touches the database: it calls back the caller with the article ids. Rejected: marking only when every message went through, which would resend the first messages of a half-sent digest the next day.
- **Failures**: a message refused on its own (400, e.g. invalid HTML) is skipped and the others go on; a temporary error (429 with Telegram's `retry_after`, 5xx, timeout, network) is retried twice (2 s, 8 s, or `retry_after` capped at 60 s), then sending stops; a fatal error (401 bad token, 403 bot blocked, 404, a redirect) stops at once. Unsent articles compete again for the next digest.
- **The token never leaks**:
  - no httpx error is passed on: each one is rebuilt from its type only, with `raise ... from None`, so it is not chained into a traceback either (httpx errors contain the URL);
  - httpx logs every request URL itself (logger `httpx`, INFO): while a client is open, a filter on that logger replaces the token with `<token>`, whatever the log level;
  - Telegram's error descriptions are cleaned, and checked for the token;
  - redirects are never followed; `TelegramSettings` hides the token from `repr`.
  GitHub masks secrets in Actions logs, but only their exact value: this design does not rely on it.

## Consequences

- A half-sent digest never duplicates: the next digest holds only what was not confirmed.
- The token-leak paths found while writing this (httpx's own request log, chained exceptions) are each covered by a test, and checked by injecting the leak back.
- Deploying from a separate private repository stays an option for step 7 (private run logs, a database that can be committed); the code does not depend on it.
