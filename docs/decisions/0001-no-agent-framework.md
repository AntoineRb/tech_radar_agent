# 0001. Build the agent loop without a framework

- Status: Accepted
- Date: 2026-09-28

## Context

The project is a learning exercise that follows the Hugging Face Agents Course. Frameworks like LangChain or CrewAI hide the loop that makes an agent an agent.

## Decision

The collect → score → decide → act loop is written by hand in plain Python. LLM APIs are called directly.

## Consequences

- Every step of the loop is visible and easy to debug.
- Retries, rate limiting and prompt handling have to be written by hand.
