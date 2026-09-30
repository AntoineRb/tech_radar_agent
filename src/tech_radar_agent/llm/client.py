"""Generic client for any server speaking the OpenAI chat completions format (ADR 0008).

This module knows HTTP and the response format. It knows NOTHING about scoring, summaries or
your interest profile: those live in another module that receives an LlmClient.

Request (what the server expects):
    POST {base_url}/chat/completions
    Authorization: Bearer <api_key>          <- only if there is a key
    JSON body: {"model": "...", "messages": [...], ...optional fields}

Response (what you get back, trimmed):
    {"choices": [{"message": {"role": "assistant", "content": "the answer"}}],
     "usage": {"prompt_tokens": 48, "completion_tokens": 2, ...}}

SKELETON: replace every `raise NotImplementedError` and TODO. Delete these guide comments as you go
(keep the ones that explain *why*).
"""

import logging
from typing import Any

import httpx

from tech_radar_agent.llm.settings import LlmSettings

logger = logging.getLogger(__name__)

# A message of the conversation: {"role": "system" | "user" | "assistant", "content": "..."}.
Message = dict[str, str]

# TODO: choose the timeout (seconds) for one LLM call. Numbers measured on your Mac with qwen3.6:
#   - warm model, reasoning off: ~0.3 s
#   - warm model, reasoning on: ~18 s
#   - first call (model loading into memory): ~20 s
#   - collectors use 10 s: is that enough here?
REQUEST_TIMEOUT = ...


class LlmError(Exception):
    """The LLM could not give a usable answer.

    One single error type for every failure (network, timeout, HTTP status, unexpected response),
    so callers only need `except LlmError`.
    """


class LlmClient:
    """Sends conversations to the LLM described by LlmSettings. One instance per run.

    Usage (what the rest of the code will write):
        with LlmClient(load_llm_settings()) as llm:
            text = llm.chat([{"role": "user", "content": "Hello"}])
    """

    def __init__(self, settings: LlmSettings, transport: httpx.BaseTransport | None = None) -> None:
        """
        Input:
            settings: base_url, model, api_key (already validated: https, or http on localhost only).
            transport: None in real use. In tests, an httpx.MockTransport (like `fake_http` does).
        Output: nothing, but the instance is ready to send requests.

        TODO:
        - Keep what `chat()` will need later (attributes).
        - Create ONE httpx.Client here, reused by every call (not one per call: why?).
            * `httpx.Client` accepts `base_url=`: then requests only need the path "/chat/completions".
            * Headers: the Authorization header only when there is an api_key.
            * Timeout: REQUEST_TIMEOUT.
            * Pass `transport` through (like `http_client()` in collectors/base.py).
        - Security: never log the api_key, never put it anywhere else than the header.
        """
        raise NotImplementedError

    def chat(self, messages: list[Message], **options: Any) -> str:
        """Send a conversation and return the assistant's answer.

        Input:
            messages: the conversation, usually one "system" message + one "user" message.
            options: optional fields added to the request body, chosen by the caller per task.
                Examples: temperature=0, max_tokens=200, reasoning_effort="none".
        Output:
            The answer text (str), never empty.
        Raises:
            LlmError for any failure.

        TODO, step by step:
        1. Build the JSON body: model + messages + options.
           Question: what should happen if `options` also contains "model" or "messages"?
        2. Send the POST request.
           Question: which httpx exceptions can happen (connection, timeout, bad status)?
           Wrap them into LlmError and keep the original cause (look up `raise ... from ...`).
           Remember `response.raise_for_status()`.
        3. Read the text at choices[0].message.content.
           Any missing step (no "choices", empty list, no "message", content None, invalid JSON)
           -> LlmError. Security rule: reject, never guess.
        4. Blank answer ("", "   ") -> LlmError.
        5. Optional but useful: logger.debug() the duration and the token usage.
           Never log the key. Avoid logging whole prompts at INFO level (they contain your profile).
        """
        raise NotImplementedError

    def close(self) -> None:
        """Release the connection. TODO: close the httpx.Client."""
        raise NotImplementedError

    def __enter__(self) -> "LlmClient":
        """Called by `with LlmClient(...) as llm:`. TODO: what should `llm` be?"""
        raise NotImplementedError

    def __exit__(self, *exc_info: object) -> None:
        """Called when leaving the `with` block, even after an exception. TODO: clean up."""
        raise NotImplementedError


# OPEN QUESTION (decide before coding chat()):
# `reasoning_effort="none"` makes qwen3.6 60x faster, but a remote provider may reject that field.
# Where should this setting come from?
#   (A) the caller passes it in `options` for each task (the scorer decides);
#   (B) a new optional environment variable, e.g. LLM_REASONING_EFFORT, stored in LlmSettings
#       and added to every request by the client (that part is plumbing: ask Claude);
#   (C) something else?
# Think about: who knows whether the server supports it? The code, or where it is deployed?
