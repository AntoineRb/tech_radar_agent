# 0015. Prompt changes are decided on measurements against a real model

- Status: Accepted
- Date: 2026-10-04

## Context

Prompt wording has large, non-obvious effects. Several "obvious" improvements made things worse when tested: a longer summary prompt broke the JSON format in 8 answers out of 12; "plain text" was read as the format of the whole reply; "keep terms untranslated" produced summaries in English.

## Decision

- A prompt change is compared with the previous version **on the same articles**, real ones and crafted ones (injection, excluded topic, too-thin content, cut-off content), with simple counts: invalid answers, wrong language, scores in the expected range, spread.
- The **why** of each section, and the measurement behind it, is kept as a comment next to the prompt.
- **The local model is a shared resource**: qwen3.6 needs about 23 GB of RAM. Real-model checks are small (a few articles), run only when needed, and never as large batches.
- A firmer instruction that measurably hurts a more important property is dropped (for example, a rule against "The article…" openings in French summaries that broke JSON).

## Consequences

- The scoring prompt went from 6/7 to 7/7 crafted cases right, with a better score spread; the summary prompt from 1 to 0 invalid answers, with no invented summary for thin text.
- These checks are ad hoc scripts today. The next step is a reproducible evaluation set (expected scores for a fixed set of articles), also useful to recalibrate the summary threshold when changing models.
