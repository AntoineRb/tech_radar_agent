# Collectors

Defined in [`src/tech_radar_agent/collectors/`](../../src/tech_radar_agent/collectors/). A collector fetches one source and turns what it finds into [`Article`](data-model.md) objects. Collectors never touch the database.

The design is not tied to tech news. Any source that can produce a title and a URL (news site, API, mailbox, local files…) can become a collector. See [ADR 0006](../decisions/0006-pluggable-collectors.md).

## Building blocks

| Piece | File | Role |
|---|---|---|
| `Collector` | `base.py` | Abstract base class: a `type`, a `name`, and a `collect() -> list[Article]` method |
| `http_client()` | `base.py` | `httpx.Client` with the shared settings (10 s timeout, User-Agent, redirects) |
| `fetch()` / `fetch_json()` | `base.py` | The only way to download: HTTPS only (even after redirects), 5 MB maximum. Raise `UnsafeResponseError` (an `httpx.HTTPError`) otherwise |
| `html_to_text()` | `base.py` | Turns an HTML snippet into plain text for the LLM |
| `COLLECTOR_TYPES` | `__init__.py` | Registry: config `type` → collector class |
| `build_collector(config)` | `__init__.py` | Creates a collector from one config entry |

## From config to collector

Each source is a dict. `type` selects the class. Every other key is passed to its constructor:

```python
from tech_radar_agent.collectors import build_collector

collector = build_collector({"type": "hackernews", "name": "hn-best", "feed": "best", "limit": 50})
articles = collector.collect()
```

- `name` becomes `Article.source`. It defaults to the type. Set it when several sources share a type (for example one per RSS feed).
- Errors show up when the collector is built, before any network call: an unknown `type` or an invalid value raises `ValueError`, and a misspelled option raises `TypeError`.

## Error handling

- If the whole source is unreachable, `collect()` **raises**. Deciding what to do then (log it and move on to the next source) is the job of the orchestrator.
- If a single item fails, it is **logged and skipped**. The rest of the batch is still returned. This includes items rejected by `Article`'s security checks (`ValueError`).

## Available collectors

### `hackernews`

Uses the [official Hacker News API](https://github.com/HackerNews/API), maintained by Y Combinator and served over HTTPS from `hacker-news.firebaseio.com`. It first fetches the list of story ids, then fetches each story in parallel.

| Option | Default | Meaning |
|---|---|---|
| `name` | `"hackernews"` | Value stored in `Article.source` |
| `feed` | `"top"` | `top`, `new`, `best`, `ask` or `show` |
| `limit` | `30` | Number of stories fetched, before filtering |
| `min_points` | `0` | Drop stories below this score |
| `max_workers` | `10` | Parallel requests |

Mapping to `Article`:

| `Article` | From the HN item |
|---|---|
| `title`, `author` | `title`, `by` |
| `url` | `url`, or the discussion page for posts without a link ("Ask HN") |
| `content` | `text` (HTML converted to plain text), `None` for link posts |
| `published_at` | `time` (Unix timestamp → UTC `datetime`) |
| `extra` | `hn_id`, `points`, `comments`, `discussion_url` |

The collector skips deleted or dead items, as well as anything that is not a `story` (jobs, polls, comments).

Fetching 40 stories takes about 1 second.

### `rss`

Reads one RSS or Atom feed (RSS 0.9x/1.0/2.0, Atom, and arXiv feeds). The feed is downloaded with `fetch()`, then parsed offline by [`feedparser`](https://github.com/kurtmckee/feedparser). Use one entry per feed, each with its own `name`.

| Option | Default | Meaning |
|---|---|---|
| `url` | **required** | HTTPS URL of the feed, published by the publisher's own site |
| `name` | `"rss"` | Value stored in `Article.source`. Always set it, since there will be many feeds |
| `limit` | `30` | Keep the first (most recent) entries only. Useful for noisy feeds like arXiv |

Mapping to `Article`:

| `Article` | From the feed entry |
|---|---|
| `title` | `title` (HTML converted to plain text) |
| `url` | `link`. Entries without a link are skipped |
| `author` | `author` |
| `content` | Atom `content` if present, otherwise `summary` / `description`, as plain text |
| `published_at` | `published`, or `updated` if there is no `published` (UTC) |
| `extra` | `feed_title`, `tags` |

Security notes:

- `feedparser` disables external XML entities, so there is no XXE. It also removes `<script>` and other dangerous HTML before we convert the HTML to text.
- A malformed feed (`bozo`) is accepted as long as some entries can be read. If nothing can be read, `collect()` raises.

Tested on Lobsters (RSS 2.0), Simon Willison (Atom) and arXiv cs.AI.

### `github`

Returns recently created repositories, sorted by stars, using the [GitHub Search API](https://docs.github.com/en/rest/search/search#search-repositories). GitHub has no official "trending" API, and scraping the HTML trending page would be fragile. This is the closest reliable equivalent.

| Option | Default | Meaning |
|---|---|---|
| `name` | `"github"` | Value stored in `Article.source` |
| `query` | `""` | Extra [search qualifiers](https://docs.github.com/en/search-github/searching-on-github/searching-for-repositories), e.g. `"language:python topic:llm"` |
| `created_within_days` | `7` | Only repositories created in this time window |
| `min_stars` | `50` | Minimum star count |
| `limit` | `30` | Number of repositories, from 1 to 100 (one API page) |

Mapping to `Article`:

| `Article` | From the repository |
|---|---|
| `title` | `full_name` (`owner/name`) |
| `url` | `html_url` |
| `author` | `owner.login` |
| `content` | `description` |
| `published_at` | `created_at` |
| `extra` | `stars`, `language`, `topics` |

The collector works without authentication (10 searches per minute, which is plenty for a daily run). If the `GITHUB_TOKEN` environment variable is set, it is sent as a Bearer token to get a higher rate limit. GitHub Actions provides this variable automatically. The token only comes from the environment, and it is never logged.

## Adding a new source

0. Check the source against the [security rules](../security.md): it must be an official API or publisher feed, served over HTTPS, and linked to its documentation here.
1. Create `collectors/<source>.py` with a subclass of `Collector`. Set `type`, and take the options as keyword arguments in `__init__` (call `super().__init__(name)`).
2. Implement `collect()`. Use `http_client()` with `fetch()` / `fetch_json()` for HTTP, never `client.get`. Catch `ValueError` when building each `Article` and skip that item. Put any source-specific data in `extra`.
3. Add the class to `COLLECTOR_TYPES` in `collectors/__init__.py`.
4. Document its options on this page.
