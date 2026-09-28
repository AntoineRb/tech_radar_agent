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
| — | `feature/sqlite-storage` | SQLite storage (in progress) |
