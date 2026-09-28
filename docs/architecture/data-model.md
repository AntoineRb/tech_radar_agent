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

Source-specific data goes into `extra` so the shared schema stays small (see [ADR 0004](../decisions/0004-source-specific-data-in-extra.md)).

The LLM results (`score`, `summary`) are not fields of `Article` yet. They are stored in the database. Whether they should also live on `Article` will be decided when the scoring loop is built.

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
