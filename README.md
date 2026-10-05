# Tech Radar Agent

[![Tests](https://github.com/AntoineRb/tech_radar_agent/actions/workflows/tests.yml/badge.svg?branch=dev)](https://github.com/AntoineRb/tech_radar_agent/actions/workflows/tests.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-blue)
![No agent framework](https://img.shields.io/badge/agent%20framework-none-success)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**An AI agent that reads developer news for you, and sends you only what matters to *you*: a 5-minute digest on Telegram, every morning.**

Every day it collects articles from Hacker News, GitHub, tech blogs and arXiv, asks an LLM to judge each one against your interest profile, summarizes the best, and fits them into the time you have. It is written **from scratch, without any agent framework**: no LangChain, no CrewAI, no SDK. The whole agent loop is one readable file, every design choice is documented, and the key ones are measured.

> **Status.** v0.2.0 is released: collection, LLM scoring and summaries work end to end, with a local model ([Ollama](https://ollama.com)) or any OpenAI-compatible API. On `dev` for v0.3.0: the digest is selected and rendered (below). **Next: sending it on Telegram every morning**, scheduled with GitHub Actions.

## What you get every morning

A digest you can scan in the time of a coffee, in your own language, right on your phone:

<p align="center">
  <img src="docs/images/digest-telegram.jpg" width="380"
       alt="A Tech Radar digest in Telegram on a phone. Header: Tech Radar, Tuesday 6 October, 3 articles, about 1 min to scan. Under TO READ, each entry shows a colored badge with its score (9/10, 8/10), the article title as a link, clickable hashtags such as #ai_agents and #python with the source, an italic line starting with Why, and the summary in a quote block: the first one unfolded, the second folded.">
</p>

<p align="center"><sub>Rendered by the agent and sent by its Telegram bot. The Python 3.15 entry is a real result, translated from French; the other entries are illustrative.</sub></p>

- **Each title links to the article**, and Hacker News entries add a link to the discussion.
- **The reason says why it matters to you**; the summary says what the article brings, folded until you tap it.
- **Hashtags are clickable** in Telegram: tap `#ai_agents` to see every past entry on that topic.
- **The digest fits your reading time** (5 minutes by default): the best articles go first, and what does not fit comes back tomorrow.
- **A quiet day still gets one line**, so silence never hides a broken run: *"Nothing scored 8 or more today: 61 new articles, 3 scored, best score 5."* (a real report from the first run).

## See it in action

One command collects from 17 sources, then scores what is new:

```text
$ uv run --env-file .env tech-radar-agent
INFO    tech_radar_agent: hackernews: 26 new articles
INFO    tech_radar_agent: lobsters: 12 new articles
INFO    tech_radar_agent: arxiv-cs-ai: 15 new articles
...
INFO    tech_radar_agent: Done: 218 articles collected, 61 new, 0/17 sources failed
INFO    tech_radar_agent: Scoring with qwen3.6:latest: 3/3 articles scored (0 summarized, 0 summary failures), 0 failed
```

Real results from the first runs (qwen3.6, local, October 2026). The agent writes in the reader's language set in the profile, French here, translated below:

| Score | Article | Matched interests | Why, according to the agent |
|:---:|---|---|---|
| **8** | The Real Python Podcast #313: Python 3.15, Exploring the New Features | `python` | Technical article on the new features of Python 3.15, relevant for a Python developer. |
| 7 | AI is changing developer work. Here are three skills to strengthen. | `ai-agents`, `dev-tooling` | Article on the impact of AI on development, relevant to AI agents but lacking technical depth. |
| 5 | Apple and a Hacker's Future | `apple` | Title related to Apple (medium interest), but the content looks like an opinion essay with no technical substance for a developer. |
| 2 | Reverse Engineering Comanche Terrain Maps | none | Retro-computing topic with no direct link to the reader's high-priority technical interests. |

Articles scored 8 or more also get a summary of **what they bring**, so you can decide without opening them:

> The article announces the release of Python 3.15 and presents related learning resources, including a showcase tutorial written by Bartosz Zaczyński and a video course by Christopher Trudeau. These cover the new features of the language.

Everything lands in SQLite, then the best articles go into the digest above:

```bash
sqlite3 data/tech_radar.db "SELECT score, title, reason FROM articles WHERE score >= 8 ORDER BY scored_at DESC"
```

## An agent, without a framework

Frameworks hide the part worth understanding. Here the loop is plain Python: **perceive** (collect), **judge** (score), **decide** (threshold, retry or stop), **act** (summarize, save). This is its core, simplified from [`agent/loop.py`](src/tech_radar_agent/agent/loop.py):

```python
for stored in fetch_articles_to_score(conn, max_age_days, limit):     # recent, unscored, newest first
    try:
        score = call_with_retry(lambda: scorer.score(stored.article))  # temporary errors: wait, retry
    except (LlmTemporaryError, LlmFatalError):
        break                                                          # server down: stop, lose nothing
    except LlmError:
        continue                                                       # bad answer: skip this article

    summary = None
    if score.score >= threshold:
        summary = call_with_retry(lambda: summarizer.summarize(stored.article))

    save_score(conn, stored.id, score)                                 # committed at once
    if summary:
        save_summary(conn, stored.id, summary)
```

```mermaid
flowchart LR
    A["Collect<br/>HN, GitHub, RSS, arXiv"] --> B["Score<br/>LLM vs your profile"]
    B --> C{"Score 8+ ?"}
    C -- "yes" --> D["Summarize<br/>what it brings"]
    C -- "no" --> M["Remember<br/>SQLite"]
    D --> M
    M --> S["Select<br/>fits your reading time"]
    S --> R["Render<br/>Telegram, your language"]
    R -.-> E["Deliver<br/>Telegram, next"]
    E -.-> F["Adapt<br/>your feedback, later"]
    F -.-> B
```

The LLM client is ~260 lines of `httpx` speaking the OpenAI chat completions format, so the same code runs against a local model or a remote API: only environment variables change.

## Design choices, measured

Each choice was tested against a real model before being kept. Details are in the [decision log](docs/decisions/README.md) (25 ADRs).

| Choice | Measurement |
|---|---|
| Turn the model's "thinking" off | **0.3 s** per call instead of 18 s: about 1 minute instead of 1 hour for 200 articles |
| Send the first 1,000 characters, not the whole article | less than 1 point of difference on a 0-10 score, **~45 % fewer tokens** on long articles (30 articles) |
| Validate the LLM's JSON strictly in code, rather than trusting a server-side schema | 0 invalid answers in ~200 calls, and the validation stays the real guarantee |
| Summary threshold at 8 | keeps about a third of the articles (25 articles measured); at 7, more than half pass |
| Retry only when a retry can change something | at temperature 0, a bad answer stays bad; a server outage does not |
| Score each article alone, never in batches | no article can inject instructions into another one's judgment |
| Size the digest in minutes, not in articles | 5 minutes holds about 25 entries: on a normal day the score threshold does the filtering, and the budget caps busy days |
| Telegram rather than WhatsApp | WhatsApp's official API requires pre-approved templates for messages the agent starts, and charges per message |

## Security: collected content is data, never instructions

An agent that reads the web reads hostile text. The rules are in [`docs/security.md`](docs/security.md) and enforced by code and tests:

- **Prompt injection**: article text is cleaned (invisible and bidirectional characters removed), truncated, and isolated between delimiters in the user message. The system message holds only trusted instructions.
- **No tools for the LLM, enforced by code**: the client refuses tool options and rejects any answer containing a tool call.
- **The LLM's output is untrusted too**: the score is bounded, unknown interest ids are rejected, and a summary containing a link or HTML is rejected, never "cleaned up". Links shown to the reader always come from the database, never from the LLM.
- **The digest escapes everything**: titles, reasons, summaries and even translated labels are escaped before going into Telegram HTML, URLs included, and every block is checked to be complete HTML with Telegram's tags only.
- **Network**: HTTPS only, timeouts, 5 MB response cap, `http`/`https` URLs only, `yaml.safe_load` only.
- **Supply chain**: 3 runtime dependencies, a lockfile with hashes, `pip-audit` before dependency changes, GitHub Actions pinned to commit SHAs with a read-only token.

## Engineering

- **817 tests in ~0.4 s**, with no network and no LLM: fake HTTP servers, a fake LLM server, and hostile inputs (XXE feeds, `javascript:` links, prompt injection, links hidden by invisible characters, HTML injected into digest entries).
- **Tests checked by injecting bugs**: 56 bugs planted one at a time in the agent loop, `main()`, the digest selection, its rendering and the translations, every one caught (two of them only after strengthening the tests).
- **CI** on every pull request and push, with GitHub Actions.
- **Failure handling with clear outcomes**: one broken source never stops the others, an LLM outage never loses the day's collection, and exit codes tell CI what happened.
- **Documented**: architecture pages and one ADR per decision, under [`docs/`](docs/README.md).

## Getting started

**Prerequisites:** [uv](https://docs.astral.sh/uv/getting-started/installation/), and an LLM server speaking the OpenAI chat completions format: a local model with [Ollama](https://ollama.com), or a remote API.

```bash
git clone https://github.com/AntoineRb/tech_radar_agent.git
cd tech_radar_agent
uv sync
cp .env.example .env   # then set LLM_BASE_URL and LLM_MODEL (see docs/configuration.md)
uv run --env-file .env tech-radar-agent
```

uv installs the right Python version and every dependency from `uv.lock`. Without LLM settings, the run still collects, then skips scoring and exits with code `3`.

Describe what you care about in [`config/interests.yaml`](config/interests.yaml), in plain words:

```yaml
profile:
  about: >
    Software developer. Building AI agents from scratch in Python and following
    the tech industry closely. Interested in hands-on, technical content over hype.
  language: French
  interests:
    high:
      ai-agents: AI agents (architecture, tool use, memory, evaluation)
      llm: Large language models (new models, benchmarks, prompting, fine-tuning)
      python: Python (language, tooling, notable libraries)
  not_interested:
    - Opinion pieces with no technical substance

digest:
  reading_time_minutes: 5   # the time you have each morning
```

Labels follow your language when a translation exists (English and French today). Adding one is a single JSON file that any LLM can translate: see [configuration](docs/configuration.md#digest-labels-in-your-language).

## Project structure

```text
tech_radar_agent/
├── src/tech_radar_agent/
│   ├── agent/           # the loop, scoring, summaries, digest selection and rendering
│   ├── i18n/            # digest labels, one JSON file per language
│   ├── llm/             # LLM settings and client (httpx, no SDK)
│   ├── collectors/      # one module per source type
│   ├── storage/         # SQLite persistence
│   └── models.py        # the Article data model
├── config/
│   └── interests.yaml   # your interest profile and sources
├── docs/                # architecture, decision log, dev guides
├── tests/               # pytest suite
└── pyproject.toml
```

## Known limitations

- The digest is not sent yet: it is selected and rendered, and Telegram delivery comes next (v0.3.0).
- Summary faithfulness is not measured yet. In the example above, "Python 3.15 is (almost) here" became "announces the release". An evaluation set is planned.
- Articles without text (many Hacker News links) are judged on their title, source and domain only.
- Deduplication is by URL: the same story on two sites is not merged yet.

## Roadmap

- [x] **v0.1.0: Collection.** `Article` model, SQLite storage, collectors for Hacker News, RSS / Atom and GitHub, config-driven sources.
- [x] **v0.2.0: Agent loop.** LLM client, scoring against the interest profile, summaries, retries and failure handling, CI.
- [ ] **v0.3.0: The daily digest.**
  - [x] Sent-item tracking, so an article is never sent twice.
  - [x] Selection within a reading-time budget: best first, nothing lost, never empty.
  - [x] Rendering in Telegram HTML, in the reader's language, everything escaped.
  - [ ] Delivery on Telegram.
  - [ ] A daily run on GitHub Actions.
- [ ] **v0.4.0: Feedback and adaptation.** 👍 / 👎 on digest items, feedback-aware scoring, recurring "hot topics".
- [ ] **Alongside:** an LLM evaluation set to compare prompts and models reproducibly.

## How this project is built

Built in mentor mode with [Claude Code](https://claude.com/claude-code): I design and write the agent logic myself; Claude challenges the design one question at a time, reviews my code, and writes plumbing and tests when I ask. The working rules are in [`CLAUDE.md`](CLAUDE.md).

The project follows the [Hugging Face Agents Course](https://huggingface.co/learn/agents-course): a hands-on way to apply its core ideas (the perception, decision, action loop, memory, evaluation) to a tool I use every day.

## License

[MIT](LICENSE) © 2026 Antoine ROBERT
