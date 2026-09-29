# Development setup

The project uses Python 3.12, managed by [uv](https://docs.astral.sh/uv/). Always go through `uv`: no `pip`, and no manual virtualenv activation.

| Task | Command |
|---|---|
| Install or sync dependencies | `uv sync` |
| Run the agent | `uv run tech-radar-agent` |
| Add a dependency | `uv add <package>` |
| Add a dev-only tool | `uv add --dev <package>` |
| Run the tests | `uv run pytest` |
| Run a one-off Python snippet | `uv run python -c "..."` |

The `tech-radar-agent` command is declared in `pyproject.toml` (`[project.scripts]`) and points to `tech_radar_agent:main`.

## Dependencies

| Package | Role |
|---|---|
| `httpx` | HTTP requests to source APIs |
| `feedparser` | RSS and Atom parsing |
| `pyyaml` | Reading `config/interests.yaml` |
| `pytest` (dev only) | Tests |

## Tests

See [testing.md](testing.md). There is no linter yet.
