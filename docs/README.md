# Documentation

Technical documentation for Tech Radar Agent. For a quick introduction, see the [project README](../README.md).

```text
docs/
├── README.md                 # this index
├── security.md               # security rules: dependencies, sources, prompt injection
├── architecture/
│   ├── overview.md           # pipeline and code layout
│   ├── data-model.md         # the Article model and URL normalization
│   ├── collectors.md         # source plugins and how to add one
│   └── storage.md            # SQLite schema and storage API
├── decisions/                # one file per architecture decision (ADR)
│   └── README.md             # decision log
└── development/
    ├── setup.md              # install, run, add dependencies
    └── git-workflow.md       # branches and merge requests
```

## Security

[Security rules](security.md) that every dependency, source and pipeline step must follow.

## Architecture

- [Overview](architecture/overview.md): the collect → score → summarize → deliver pipeline and where each part lives.
- [Data model](architecture/data-model.md): `Article`, the object that flows through the whole pipeline.
- [Collectors](architecture/collectors.md): how sources are plugged in and configured.
- [Storage](architecture/storage.md): how articles are persisted and deduplicated in SQLite.

## Decisions

The [decision log](decisions/README.md) records each architecture choice with its context and trade-offs.

## Development

- [Setup](development/setup.md)
- [Git workflow](development/git-workflow.md)
