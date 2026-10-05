# Data model

Defined in [`src/tech_radar_agent/models.py`](../../src/tech_radar_agent/models.py).

## `Article`

An `Article` describes **what a collector brings back**, before any LLM processing. It is a standard library `dataclass` (see [ADR 0002](../decisions/0002-article-as-dataclass.md)).

| Field | Type | Required | Notes |
|---|---|---|---|
| `source` | `str` | yes | Name of the collector instance: `"hackernews"`, `"hn-best"`, `"rss-lobsters"`… (see [collectors](collectors.md)). |
| `title` | `str` | yes | |
| `url` | `str` | yes | Original URL, used as the link in the digest. |
| `author` | `str \| None` | no | |
| `content` | `str \| None` | no | Text excerpt for the LLM. `None` for link-only posts. |
| `published_at` | `datetime \| None` | no | Not every source provides a date. |
| `fetched_at` | `datetime` | auto | UTC timestamp set when the object is created. |
| `extra` | `dict[str, Any]` | auto | Source-specific data (HN points, GitHub stars…). Empty by default. |

### Validation on creation

Collected data is untrusted, so `Article.__post_init__` checks it before the object exists (see [security](../security.md)):

- `url` must use `http` or `https` and have a host. Otherwise `ValueError` is raised.
- `title` (max 300 chars), `author` (max 100) and `content` (max 3,000) are cleaned by `sanitize.clean_text()`: hidden Unicode characters are removed, the text is normalized, whitespace is collapsed and the text is truncated.
- An empty title after cleaning raises `ValueError`.

Collectors catch the `ValueError`, log it and skip the item.

Source-specific data goes into `extra` so the shared schema stays small (see [ADR 0004](../decisions/0004-source-specific-data-in-extra.md)).

The LLM results (`score`, `reason`, `interests`, `summary`) are not fields of `Article`: `Article` describes what the collection brings back. The [agent loop](agent-loop.md) gets them from `Scorer` and `Summarizer` and writes them to the database with `save_score` and `save_summary`, using the id from `StoredArticle`.

## `normalized_url`: the deduplication key

`Article.normalized_url` is a computed property that calls `normalize_url(url)`. Because it is computed from `url`, the two values can never get out of sync. See [ADR 0003](../decisions/0003-dedup-by-normalized-url.md) for the reasoning.

`normalize_url` makes these changes:

| Transformation | Example |
|---|---|
| Lowercase scheme and domain | `HTTPS://Example.COM/a` → `https://example.com/a` |
| Strip trailing `/` | `https://example.com/a/` → `https://example.com/a` |
| Drop the `#fragment` | `https://example.com/a#intro` → `https://example.com/a` |
| Remove tracking parameters (`utm_*`, `fbclid`, `gclid`, `ref`, `ref_src`, `mc_cid`, `mc_eid`) | `…/a?utm_source=hn` → `…/a` |
| Sort the remaining parameters | `?b=2&a=1` → `?a=1&b=2` |
| Keep meaningful parameters | `youtube.com/watch?v=abc` stays as is |

These cases are not handled on purpose: `www.` vs no `www.`, and `http` vs `https`. They will be handled if real duplicates get through.

These cases were checked by hand. They should become pytest tests.
