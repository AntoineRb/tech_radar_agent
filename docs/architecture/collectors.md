# Collectors

Defined in [`src/tech_radar_agent/collectors/`](../../src/tech_radar_agent/collectors/). A collector fetches one source and turns what it finds into [`Article`](data-model.md) objects. Collectors never touch the database.

The design is not tied to tech news. Any source that can produce a title and a URL (news site, API, mailbox, local files…) can become a collector. See [ADR 0006](../decisions/0006-pluggable-collectors.md).

## Building blocks

| Piece | File | Role |
|---|---|---|
| `Collector` | `base.py` | Abstract base class: a `type`, a `name`, and a `collect() -> list[Article]` method |
| `http_client()` | `base.py` | `httpx.Client` with the shared settings (10 s timeout, User-Agent, redirects) |
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
- If a single item fails, it is **logged and skipped**. The rest of the batch is still returned.

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

## Adding a new source

0. Check the source against the [security rules](../security.md): it must be an official API or publisher feed, served over HTTPS, and linked to its documentation here.
1. Create `collectors/<source>.py` with a subclass of `Collector`. Set `type`, and take the options as keyword arguments in `__init__` (call `super().__init__(name)`).
2. Implement `collect()`. Use `http_client()` for HTTP, and put any source-specific data in `extra`.
3. Add the class to `COLLECTOR_TYPES` in `collectors/__init__.py`.
4. Document its options on this page.
