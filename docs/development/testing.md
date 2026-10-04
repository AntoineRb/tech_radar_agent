# Testing

Tests use [pytest](https://docs.pytest.org/), installed as a dev-only dependency. They run in about 0.1 s, **never touch the network**, and never touch the real `data/` folder.

```bash
uv run pytest                                          # everything
uv run pytest tests/test_models.py                     # one file
uv run pytest tests/test_models.py::TestArticle        # one class
uv run pytest -k "xxe or unsafe"                       # tests whose name matches
uv run pytest -x --lf                                  # stop at first failure, rerun last failures
```

The configuration is in `pyproject.toml` (`[tool.pytest.ini_options]`).

## Layout

The `tests/` folder mirrors `src/tech_radar_agent/`:

```text
tests/
├── conftest.py              # shared fixtures: no_network, fake_http
├── test_config.py           # load_config() + checks on the real config/interests.yaml
├── test_main.py             # main(): orchestration, failures, exit codes
├── test_models.py           # normalize_url, Article (defaults, validation, cleaning)
├── test_sanitize.py         # clean_text, is_safe_url
├── test_storage.py          # connect (schema upgrade), save_articles, fetch_articles_to_score, save_score/summary
├── agent/
│   ├── test_scoring.py      # parse_score (hostile answers), article message (injection), system prompt, Scorer
│   └── test_agent_settings.py  # AGENT_* variables (not test_settings.py: that name is taken in llm/)
├── llm/
│   ├── test_settings.py     # environment variables, localhost-only http, secret handling
│   ├── test_client.py       # LlmClient: request body, response validation, errors, with-block, key never logged
│   └── test_cli.py          # python -m tech_radar_agent.llm (setup check command)
└── collectors/
    ├── test_base.py         # fetch (HTTPS only, size limit, redirects), html_to_text, Collector
    ├── test_registry.py     # build_collector, COLLECTOR_TYPES
    ├── test_hackernews.py
    ├── test_rss.py          # RSS 2.0, Atom, hostile feed (XXE, scripts, javascript: links)
    └── test_github.py       # query building, token handling
```

## Fixtures

| Fixture | Scope | What it does |
|---|---|---|
| `no_network` | every test (autouse) | Any real HTTP request fails the test at once |
| `fake_http` | on demand | Sends all collector HTTP traffic to a fake server, and records the requests |
| `tmp_path`, `monkeypatch`, `caplog` | built into pytest | Temporary folder, temporary patches, captured logs |

### `fake_http`

```python
def test_something(fake_http):
    fake_http.routes["https://example.com/api"] = {"ids": [1, 2]}   # dict/list/None -> JSON
    fake_http.routes["https://example.com/feed"] = "<rss>...</rss>"  # str/bytes -> raw body
    fake_http.routes["https://example.com/down"] = 503                # int -> status code
    fake_http.routes["https://example.com/dns"] = httpx.ConnectError("boom")  # raised
    ...
    fake_http.requests          # every httpx.Request sent
    fake_http.requested_urls()  # the same, as strings
```

A route without a query string also matches requests with one. Unknown URLs get a 404. The collectors still use the real `http_client()` settings (User-Agent, redirects) and the real `fetch()` checks. Only the network layer is replaced, through `httpx.MockTransport`.

### Testing the LLM client

`tests/llm/test_client.py` has its own small `FakeLlm` server (`server` fixture). Set `server.reply` to a response body (dict), an `httpx.Response` or an exception, call `server.client(**settings)`, then inspect `server.requests` / `server.last_body`. No Ollama or API is needed.

### Testing the scoring

`tests/agent/test_scoring.py` needs no HTTP at all. The prompt builders and `parse_score` are pure functions, tested with plain strings, `Article` and `Profile` objects (`make_article()`, `make_profile()`, `answer()` build valid inputs that each test changes one field of). `Scorer` gets a `FakeLlm`: any object with a `chat(messages, **options)` method works, so it simply records the calls and returns or raises the answer chosen by the test.

### Testing `main()`

`test_main.py` registers a `FakeCollector` (`type: fake`) in `COLLECTOR_TYPES`, then runs `main()` in an empty temporary folder. This tests the orchestration without any HTTP. `caplog.set_level(logging.INFO)` is needed there, because pytest's own log handlers make `main()`'s `basicConfig()` a no-op.

## Rules

- Test file names must be unique across folders (there is no `__init__.py` in `tests/`): `tests/llm/test_cli.py`, not a second `test_main.py`.

- **Every feature ships with its tests.** Adding or changing a feature means adding or updating the matching tests in the same merge request.
- **Every bug fix ships with a test** that fails without the fix.
- No network, no real `data/`: use `fake_http` and `tmp_path`.
- Security checks are tested with hostile input (see `test_sanitize.py`, `test_rss.py::TestSecurity`), not only with happy paths.
- `test_config.py::TestRealConfig` validates `config/interests.yaml` itself. A broken edit of the config fails the tests, not the next daily run.

## Bugs found while writing the first tests

- The RSS collector accepted a well-formed HTML page (for example a site's home page instead of its feed) and silently returned 0 articles. It now raises "not an RSS or Atom feed".
- An empty response crashed the RSS collector with an `AttributeError` (no `version` field) instead of a clear error.
