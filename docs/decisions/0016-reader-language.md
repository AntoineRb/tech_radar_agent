# 0016. Instructions in English, reader-facing text in the reader's language

- Status: Accepted
- Date: 2026-10-04

## Context

The reader reads French; the code base, the prompts and most articles are in English. The language of `reason` and `summary` had to be configurable, and the switch to English once the agent is validated had to be trivial.

## Decision

- `profile.language` in `config/interests.yaml` (a plain name such as `French`, default `English`) sets the language of everything the reader reads: `reason` and `summary`. No separate setting per field.
- Prompt instructions stay in English.
- The language instruction is repeated and placed **last** in each prompt ("Always write … in French, even though these instructions and the article are in English"), and the summary prompt says "write in French" before listing what stays as written (technical terms, names, code identifiers).

## Consequences

- Measured: French vs English reasons cost the same number of tokens and give identical scores (10 articles).
- Stated only inside the answer template, the language was ignored for some articles; placed last, 31/32 reasons came out in French. The only exception was an injection article, scored 0.
