# 0003. Deduplicate articles by normalized URL

- Status: Accepted
- Date: 2026-09-28

## Context

The same page often shows up with different URLs (tracking parameters, letter case, trailing slash, `#fragment`), or from several sources. The agent must recognize it as a single article.

Options considered:

- **Random UUID**: identifies a row, but does not detect duplicates.
- **Hash of the URL**: works, but you cannot read it when debugging.
- **Normalized URL in plain text**: works, and you can read it.

## Decision

- The deduplication key is the normalized URL, stored in plain text.
- `Article.url` keeps the original URL, which is the link shown in the digest.
- `Article.normalized_url` is a **computed property**, so it cannot get out of sync with `url`.
- In the database, `id` is `INTEGER PRIMARY KEY` and `normalized_url` is `UNIQUE`.

## Consequences

- Duplicates are rejected by the database itself.
- `www.` vs no `www.` and `http` vs `https` are not merged yet.
- Cross-source duplicates with different URLs (for example the same news story on two sites) are not detected. Title similarity may be added later.
