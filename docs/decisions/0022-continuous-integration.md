# 0022. Continuous integration: tests on every pull request and push, with pinned actions and a read-only token

- Status: Accepted
- Date: 2026-10-05

## Context

Tests were only run by hand before each merge request. The repository is public: anyone can open a pull request from a fork, and a workflow runs code from that pull request. GitHub Actions are third-party code too, and a tag such as `v7` can be moved to other code at any time.

## Decision

- One workflow, `.github/workflows/tests.yml`, runs `uv run pytest` on every **pull request** and every **push** to `dev` and `main`.
- Only two actions, both from their official owners: `actions/checkout` (GitHub) and `astral-sh/setup-uv` (Astral, the makers of uv). Each is **pinned to a full commit SHA**, with the version in a comment. The SHAs were resolved from the release tags with `git ls-remote` and checked against the official repositories (signed commits).
- The uv version is pinned as well, and dependencies are installed with `uv sync --locked`: the run fails if `uv.lock` is out of date, and every package is checked against its sha256 hash.
- **Least privilege**: `permissions: contents: read`, `persist-credentials: false` on checkout, no secret used. The trigger is `pull_request`, never `pull_request_target`, so a fork's pull request runs with a read-only token and no secrets.
- GitHub-hosted runners only, **never a self-hosted runner**: on a public repository, a fork's pull request would run code on that machine.

## Consequences

- A failing test shows on the pull request before it is merged. Making the check required is a branch protection setting on GitHub, outside the repository.
- Pinned SHAs do not update themselves. Updating an action means resolving the new release's SHA and checking it the same way (Dependabot could propose these updates later).
- The CI still does not run `ruff`, `mypy` or `pip-audit`: each one is a new tool to validate first.
