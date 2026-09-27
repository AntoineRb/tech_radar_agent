Tech Radar Agent

🚧 Work in progress. The project is being built step by step and is not usable yet. See the roadmap for the current status.

A personal tech-watch agent that scans developer news sources every day, uses an LLM to decide what is actually relevant to you, and delivers a short, curated digest.

It is built from scratch, without any agent framework (no LangChain, no CrewAI). The goal is to understand what makes an agent more than a script: a loop of collecting, judging, remembering and adapting.

Why

Hacker News, GitHub, arXiv and tech blogs produce far more content than anyone can read. Keyword filters are too blunt: they miss relevant articles and let noise through. Tech Radar Agent reads everything for you and keeps only what matches your interests, explaining in a couple of sentences why each item is worth your time.

How it works
┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
│  Collect   │──▶│   Score    │──▶│  Remember  │──▶│ Summarize  │──▶│  Deliver   │
│ HN, GitHub │   │ LLM judges │   │ dedup, seen│   │ why it's   │   │ daily      │
│ RSS, arXiv │   │ relevance  │   │ & feedback │   │ relevant   │   │ digest     │
└────────────┘   └────────────┘   └────────────┘   └────────────┘   └────────────┘
                        ▲                                                  │
                        └──────────────── your feedback 👍 / 👎 ───────────┘
Collect: fetch raw content from several sources (Hacker News API, GitHub, RSS feeds).
Score: an LLM rates each item against your interest profile, not just keywords.
Remember: store everything in SQLite to avoid duplicates and never show the same item twice.
Summarize: write a short summary explaining why the item matters to you.
Deliver: send a daily digest (email or Discord), triggered automatically by GitHub Actions.
Adapt: your feedback on past digests is fed back into the scoring, so the agent improves over time.
Tech stack
Python 3.12, managed with uv
httpx for HTTP requests, feedparser for RSS/Atom feeds
SQLite as the agent's memory
YAML for the interest profile and source configuration
LLM API for scoring and summarization (coming soon)
GitHub Actions for the daily schedule (coming soon)
Getting started

The agent does not do anything useful yet. These steps set up the development environment.

Prerequisite: uv installed.

bash
git clone https://github.com/<your-username>/tech_radar_agent.git
cd tech_radar_agent
uv sync
uv run tech-radar-agent

uv installs the right Python version and all dependencies automatically, based on .python-version and uv.lock.

Project structure
tech_radar_agent/
├── src/tech_radar_agent/
│   ├── models.py        # the Article data model
│   ├── collectors/      # one module per source
│   └── storage/         # SQLite persistence
├── config/
│   └── interests.yaml   # your interest profile and sources
├── data/                # local SQLite database (git-ignored)
└── pyproject.toml
Roadmap
 Step 1: Collection. Project setup, Article model, SQLite storage, collectors for Hacker News, RSS and GitHub.
 Step 2: Agent loop. LLM scoring against the interest profile, relevance summaries, error handling and rate limiting.
 Step 3: Memory and delivery. Cross-source deduplication, sent-item tracking, daily digest by email or Discord, scheduling with GitHub Actions.
 Step 4: Feedback and adaptation. 👍 / 👎 feedback on digest items, feedback-aware scoring, detection of recurring "hot topics".
Background

This project follows the Hugging Face Agents Course. It is a hands-on way to apply the core concepts (tool use, memory, the perception → decision → action loop) to a tool I actually use every day.