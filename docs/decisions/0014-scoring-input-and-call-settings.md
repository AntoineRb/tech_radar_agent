# 0014. Scoring input and call settings

- Status: Accepted
- Date: 2026-10-04

## Context

Scoring runs on every new article, so its input size drives cost and speed. Some article fields help judge relevance; others mislead.

## Decision

- **Sent**: source, domain, title, descriptive tags (GitHub language and topics, RSS tags, 5 at most), and the first **1,000 characters** of content, cut at the end of a word.
- **Not sent**: author and dates (no help), and popularity (HN points, GitHub stars), which the model would mistake for relevance.
- **One article per call**: batching several articles would let an injection in one article influence the scores of the others.
- **Call settings**: `temperature=0`, `max_tokens=200`, reasoning turned off (`LLM_REASONING_EFFORT=none` locally), **no `response_format`**.

## Consequences

- Measured on 30 long articles with qwen3.6: with 600 to 1,000 characters, scores are within one point of full-content scores on average, at about 45% fewer tokens; the first 300 characters (often an introduction) do not help; the title alone already gives the same above/below-threshold decision 83% of the time. Half of the stored articles have under 300 characters anyway.
- `temperature=0`: identical scores from one run to the next (measured).
- Reasoning off: about 0.3 s per call instead of about 18 s with qwen3.6.
- `response_format`: Ollama ignores the JSON schema with qwen3.6 (checked) and some providers reject the field. The prompt asking for "JSON only" gave 0 invalid answers in about 200 calls, but no model guarantees it: **validation in our code is the guarantee**. A schema can be added later as an optional extra layer.
