# Git workflow

The workflow is based on git flow, but features are merged on GitHub rather than locally.

| Branch | Role |
|---|---|
| `main` | Stable releases |
| `dev` | Integration branch, the default branch on GitHub |
| `feature/<kebab-name>` | One branch per step, created from `dev` |

## Working on a feature

```bash
git flow feature start <kebab-name>   # creates feature/<kebab-name> from dev
# ... commits ...
git push -u origin feature/<kebab-name>
```

Then open a pull request `feature/<kebab-name>` → `dev` on GitHub and merge it there.

Do **not** use `git flow feature finish`, because it merges locally and skips the review.

## History so far

| PR | Branch | Content |
|---|---|---|
| #2 | `feature/article-model` | `Article` dataclass |
| #3 | `feature/article-model` | `normalized_url` deduplication key |
| #4 | `feature/sqlite-storage` | SQLite storage |
| #5 | `feature/hackernews-collector` | Collector base class, Hacker News collector, security rules |
| #6 | `feature/rss-github-collectors` | Parsing-time security, RSS and GitHub collectors, interest profile |
| #7 | `feature/entrypoint` | `main()` orchestration and source list |
| #8 | `feature/unit-test` | pytest setup and tests for everything built so far |

Before opening a merge request, run `uv run pytest`: every test must pass. GitHub Actions runs the same tests on every pull request and push to `dev` and `main` ([CI](testing.md#continuous-integration)), and shows the result on the pull request.
