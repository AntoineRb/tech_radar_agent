# 0025. Digest labels in one JSON file per language, checked against a contract in the code

- Status: Accepted
- Date: 2026-10-05

## Context

The LLM writes reasons and summaries in `profile.language` by itself ([ADR 0016](0016-reader-language.md)). The labels written by the code around them (section titles, "Why:", the date, the activity report) must follow, or the digest mixes two languages. `profile.language` is free text ("French", "Français"), easy for an LLM to read but not a reliable key for code. The agent also runs on GitHub Actions, where system locales may be missing.

## Decision

- One JSON file per language in the package, `src/tech_radar_agent/i18n/` (`en.json`, `fr.json`), read with `importlib.resources` so the files travel with the code. The built package ships them (checked on the wheel).
- Each file declares its own `language_names`, matched against `profile.language` regardless of case (the file code, such as `fr`, matches too). No match: **English**, with a log line.
- **The contract lives in the code**, which uses the labels: `LABELS` lists every label and the placeholders it takes. Every file, English included, must match it exactly, along with 7 weekdays and 12 months. A first version checked translations against `en.json`, which let a key missing from `en.json` itself go unnoticed; a test caught it.
- An invalid translation falls back to English with a warning: a label problem must never cost the day's digest. An invalid `en.json` raises, since there is nothing left to fall back to.
- Placeholders use `string.Template` (`$minutes`), not `str.format`, which can read attributes (`{minutes.__class__}`); a translated file is text nobody here wrote.
- Weekday and month names are in the files: dates never depend on the system locale.
- Labels are plain text, escaped like any other text before going into Telegram HTML.

## Consequences

- Adding a language means adding one file, which any LLM can translate from `en.json`; the tests check it before it is merged.
- Adding a label means adding it to `LABELS` and to every file: the tests fail until all files have it.
- A language without a file still works: content in that language, labels in English.
