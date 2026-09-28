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
| — | `feature/entrypoint` | `main()` orchestration and source list (in progress) |
