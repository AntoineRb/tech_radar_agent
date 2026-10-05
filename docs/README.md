# Documentation

Technical documentation for Tech Radar Agent. For a quick introduction, see the [project README](../README.md).

```text
docs/
├── README.md                 # this index
├── configuration.md          # interests.yaml (profile, sources) and environment variables (LLM)
├── security.md               # security rules: dependencies, sources, prompt injection
├── architecture/
│   ├── overview.md           # pipeline and code layout
│   ├── data-model.md         # the Article model and URL normalization
│   ├── collectors.md         # source plugins and how to add one
│   ├── storage.md            # SQLite schema and storage API
│   ├── scoring.md            # LLM scoring: prompts, answer validation, measurements
│   ├── summary.md            # LLM summary: what it says, when there is none, link and HTML filter
│   └── agent-loop.md         # the loop: scoring, summaries, retries, stops, run report, exit codes
├── decisions/                # one file per architecture decision (ADR)
│   └── README.md             # decision log
└── development/
    ├── setup.md              # install, run, add dependencies
    ├── testing.md            # pytest, fixtures, testing rules
    └── git-workflow.md       # branches and merge requests
```

## Configuration

[Configuration](configuration.md): how to describe your interests and choose your sources.

## Security

[Security rules](security.md) that every dependency, source and pipeline step must follow.

## Architecture

- [Overview](architecture/overview.md): the collect → score → summarize → deliver pipeline and where each part lives.
- [Data model](architecture/data-model.md): `Article`, the object that flows through the whole pipeline.
- [Collectors](architecture/collectors.md): how sources are plugged in and configured.
- [Storage](architecture/storage.md): how articles are persisted and deduplicated in SQLite.
- [Scoring](architecture/scoring.md): how the LLM rates each article against the profile, and how its answer is validated.
- [Summary](architecture/summary.md): how the best articles get a short, faithful summary, and why some get none.
- [Agent loop](architecture/agent-loop.md): how articles are scored, summarized and saved, and what happens when the LLM fails.

## Decisions

The [decision log](decisions/README.md) records each architecture choice with its context and trade-offs.

## Development

- [Setup](development/setup.md)
- [Testing](development/testing.md)
- [Git workflow](development/git-workflow.md)
