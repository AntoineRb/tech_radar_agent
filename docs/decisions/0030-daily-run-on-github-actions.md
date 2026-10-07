# 0030. Daily run on GitHub Actions, the database kept as an artifact

- Status: Accepted
- Date: 2026-10-07

## Context

The agent has to run every morning without a machine of its own. GitHub Actions gives scheduled runs on hosted runners, free on a public repository. Two problems come with it: the local model cannot run there (no GPU, not enough memory), and every run starts on an empty machine, while the SQLite database is the agent's memory: what it has seen, scored and sent. Without it, every run would send the same articles again.

## Decision

- **The public repository runs the workflow** (`.github/workflows/daily-run.yml`), rather than a separate private one: it shows the deployment next to the code. At INFO level the logs hold only counts (articles per source, scored, sent), and the interest profile is already public.
- **A release runs in production, not the work in progress**: the checkout takes a tag (`ref: v0.3.1`), because a scheduled run always starts from the default branch, `dev`. Deploying a new release, or rolling back, is a one-line change, reviewed in a pull request. A tag rather than `main`: production does not change at the moment of a merge, nor after a merge into `main` by mistake.
- **The LLM is remote**: Gemini 3.1 Flash-Lite through Google AI Studio's OpenAI-compatible API. Its free tier allows 15 requests a minute and 500 a day: `LLM_MIN_INTERVAL_SECONDS=5` ([ADR 0029](0029-llm-request-pacing.md)) for the per-minute quota, and a normal run (~130 requests with `AGENT_MAX_ARTICLES_PER_RUN=100`) fits the daily one. Paid tier 1 (about 4,000 a minute, 150,000 a day) only removes the pacing. Changing tier or provider (GitHub Models) only changes repository variables.
- **The database is kept as an artifact**, one per run, for 90 days, rather than in the Actions cache (best effort, evicted after 7 days without access, keys that cannot be overwritten) or committed to the repository (a binary file growing the history every day). Each day's database can be downloaded, which gives a history of the agent's work.
- **Restored from the newest artifact of this repository's runs on the default branch**, whatever the run's conclusion. A run that failed after sending part of the digest has marked those articles, and its database is the right one. Artifacts from forks or other branches are skipped. No artifact: the agent starts with an empty database. Any other restore error fails the job, rather than running without memory.
- **Saved even when the agent failed** (`!cancelled()`), but not when the agent did not run: an upload would then replace the memory with an empty database.
- **One run at a time** (`concurrency`, never cancelled halfway), at most 60 minutes: a run cancelled by its timeout does not save the database, so the limit leaves room for a slow provider.
- **Schedule: 06:17 UTC**, for a digest around 08:00 in Paris; plus a manual trigger.
- **Settings**: the API key, the bot token and the chat id are secrets, given to the agent step only. The other settings are repository variables.
- A failed run (exit code 1, 3 or 4) fails the job: GitHub's failure email is the alert.

## Consequences

- Anyone signed in to GitHub can download the database artifacts of a public repository: public articles, their scores, reasons and sending dates. Nothing secret, but not private either. Moving to a private repository would change that, at the cost of a free-plan limit on Actions minutes.
- The daily quota sets how many articles are scored. Gemini 3.1 Flash-Lite's free tier covers a normal day (~100 new articles); a model limited to 20 requests a day would score only the 12 newest, and the others would leave the 3-day window unscored.
- On the free tier, the provider serves paid traffic first: the first run met `503 high demand` errors and stopped after 6 articles (exit code 3, digest sent, database saved). A paid tier makes this rarer.
- The workflow only appears in the Actions tab once it is on the default branch, so its first run follows the merge, and the release whose tag it checks out.
- The code, `uv.lock` and `config/interests.yaml` come from the tag: a change to the interest profile reaches production with the next release. The workflow file itself is read from `dev`, and a change to it applies at once.
- GitHub disables the schedule of a public repository after 60 days without activity.
