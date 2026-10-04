# 0010. Tests run without network or LLM, and attack the code with hostile input

- Status: Accepted
- Date: 2026-09-29

## Context

The agent talks to many external servers and to an LLM, and its security rules matter more than its happy path. Tests that hit the network or a real model are slow, flaky, cost money or RAM, and cannot reproduce rare failures (a 429, a cut-off answer, a malicious feed).

## Decision

- **pytest**, as a dev-only dependency. No other test library.
- **No network in tests**: an autouse fixture (`no_network`) makes any real HTTP request fail the test. HTTP is simulated with `httpx.MockTransport` (`fake_http` for collectors, `FakeLlm` servers for the LLM client), which keeps the real client settings and the real checks.
- **No real LLM in tests**: `Scorer` and `Summarizer` get a fake client with a `chat()` method that records calls and returns, or raises, a chosen answer.
- **Pure functions first**: prompt builders and answer parsers are plain functions, tested with plain strings.
- **Security is tested with hostile input**, not only with valid data: XXE and scripts in feeds, `javascript:` URLs, hidden Unicode characters, delimiter escapes, invented ids, duplicate JSON keys, links hidden behind invisible characters.
- **Every feature ships with its tests**, and every bug fix with a test that fails without it. `uv run pytest` must pass before any merge request.

## Consequences

- The whole suite (about 600 tests) runs in a fraction of a second, offline.
- Writing the first tests found two real bugs in the RSS collector.
- Real-model behavior (prompt quality) is not covered by these tests: it is checked separately, on purpose and on small samples (ADR 0015).
