# 0002. Model `Article` as a standard library dataclass

- Status: Accepted
- Date: 2026-09-28

## Context

Every collector produces the same kind of object, which then flows through storage, scoring and the digest. Options: `dataclass`, Pydantic model, plain `dict`.

## Decision

Use a `dataclass`. Required fields are `source`, `title` and `url`. Optional fields default to `None`: `author`, `content`, `published_at`. `fetched_at` is set automatically in UTC.

## Consequences

- No extra dependency, and the syntax is simple.
- No runtime validation. If collectors start sending bad data, Pydantic can be reconsidered.
