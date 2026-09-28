# Configuration

Everything the agent needs to know about you lives in [`config/interests.yaml`](../config/interests.yaml). The file has two sections: the interest profile, used by the LLM to score articles, and the list of sources. It is loaded by `config.load_config()` with `yaml.safe_load` (see [security](security.md)).

## `profile`: what you care about

```yaml
profile:
  about: >
    A few sentences about who you are and what you look for.
  interests:
    high:
      - AI agents (architecture, tool use, memory, evaluation)
    medium:
      - Apple (platforms, developer tools, hardware)
    low:
      - Open source projects gaining traction
  not_interested:
    - Crypto and blockchain
```

| Key | Meaning |
|---|---|
| `about` | Free text that gives the LLM some context. `>` joins the lines into one paragraph |
| `interests.high` / `medium` / `low` | Topics by priority. The scoring prompt can weigh them differently |
| `not_interested` | Topics that should lower the score, even if they match an interest |

Tips:

- Topics are free text. The LLM matches meaning rather than keywords.
- Be specific. "Apple (platforms, developer tools, hardware)" gives better results than "Apple", which would also match earnings and rumors.
- The exclusion list matters as much as the interests: it is what keeps the digest short.

## `sources`: where articles come from

A list of entries. `type` picks the collector, and every other key is one of its options. See [collectors](architecture/collectors.md) for the options of each type.

```yaml
sources:
  - type: hackernews
    feed: top
    limit: 40
    min_points: 30
  - type: rss
    name: simon-willison
    url: https://simonwillison.net/atom/everything/
    limit: 10
```

Rules:

- Each source needs a unique `name`. The name defaults to the type, so it is required as soon as a type is used twice.
- Only official APIs and feeds published by the publisher itself, over HTTPS. Check a new feed before adding it (it responds, has recent posts, and is served from the publisher's domain), and note the check date in the file.
- `limit` controls the volume of each source. Keep it low for noisy feeds such as arXiv.

## Validation

The whole configuration is checked **before any network call**. The run stops with exit code `2` in these cases:

- the file is missing or is not valid YAML;
- a YAML tag tries to build a Python object;
- `sources` is missing or empty;
- a source has an unknown `type` or a misspelled option;
- two sources have the same name.
