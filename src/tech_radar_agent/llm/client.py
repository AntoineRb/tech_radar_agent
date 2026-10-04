"""Generic client for any server speaking the OpenAI chat completions format (ADR 0008).

This module knows HTTP and the response format. It knows NOTHING about scoring, summaries or
the interest profile: those live in another module, which receives an LlmClient.

Request (what the server expects):
    POST {base_url}/chat/completions
    Authorization: Bearer <api_key>          <- only if there is a key
    JSON body: {"model": "...", "messages": [...], ...optional fields}

Response (what comes back, trimmed):
    {"choices": [{"message": {"role": "assistant", "content": "the answer"}, "finish_reason": "stop"}],
     "usage": {"prompt_tokens": 48, "completion_tokens": 2, ...}}
"""

import logging
import re
import time
from typing import Any

import httpx

from tech_radar_agent.llm.settings import LlmSettings
from tech_radar_agent.sanitize import clean_text

logger = logging.getLogger(__name__)

# A message of the conversation: {"role": "system" | "user" | "assistant", "content": "..."}.
Message = dict[str, str]

# Body fields managed by the client: a caller cannot override them through `options`.
_RESERVED_KEYS = frozenset({"model", "messages"})

# Security rule: the LLM gets no tools (docs/security.md). It can only return text, which this
# program treats as data. These request fields would let the model ask us to run something.
_FORBIDDEN_KEYS = frozenset({"tools", "tool_choice", "parallel_tool_calls", "functions", "function_call"})

# Thinking block that some models write into their answer (compiled once).
_THINK_BLOCK = re.compile(r"<think>.*?</think>", flags=re.DOTALL)


class LlmError(Exception):
    """The LLM could not give a usable answer.

    One single error type for every failure (network, timeout, HTTP status, unexpected response),
    so callers only need `except LlmError`.
    """


class LlmClient:
    """Sends conversations to the LLM described by LlmSettings. One instance per run.

    Usage:
        with LlmClient(load_llm_settings()) as llm:
            text = llm.chat([{"role": "user", "content": "Hello"}])
    """

    def __init__(self, settings: LlmSettings, transport: httpx.BaseTransport | None = None) -> None:
        """
        Args:
            settings: base_url, model, api_key (already validated: https, or http on localhost only),
                reasoning_effort (str or None), request_timeout (float, in seconds).
            transport: None in real use. In tests, an httpx.MockTransport (a fake server).
        """
        # What chat() needs on every call.
        self._model = settings.model
        self._reasoning_effort = settings.reasoning_effort

        # One HTTP client for the whole run: it keeps the connection open between calls.
        # The API key only lives in this header: never in an attribute or a log.
        self._http_client = httpx.Client(
            base_url=settings.base_url,
            headers={"Authorization": f"Bearer {settings.api_key}"} if settings.api_key else {},
            timeout=settings.request_timeout,
            transport=transport,  # None = real network; a fake server in tests.
            follow_redirects=False,  # Never follow: a redirect could send prompts elsewhere.
        )

    def chat(self, messages: list[Message], **options: Any) -> str:
        """Send a conversation and return the assistant's answer.

        Args:
            messages: the conversation, usually one "system" message and one "user" message.
            options: optional fields added to the request body, chosen by the caller per task,
                e.g. temperature=0, max_tokens=200. A None value means "do not send this field".
        Returns:
            The answer text, stripped and never empty.
        Raises:
            LlmError: for any LLM failure.
            TypeError: if the caller passes a reserved option (a bug in the calling code).
        """
        # Built before the `try`: a reserved option is a caller bug, not an LLM failure,
        # so it must not become an LlmError.
        body = self._build_body(messages, options)

        # --- 1. Send the request: every network and HTTP error becomes an LlmError ---
        # Measured here rather than with response.elapsed, which is not available with every transport.
        started = time.perf_counter()
        try:
            response = self._http_client.post("/chat/completions", json=body)
            # Raises HTTPStatusError for any non-2xx status: 401 (bad key), 429 (rate limited),
            # 500 (server error), and also 3xx (redirects, since they are not followed).
            response.raise_for_status()
        # Order matters: TimeoutException is a subclass of RequestError, so it must come first.
        except httpx.TimeoutException as exc:
            # `from exc` keeps the original error as __cause__, visible in the traceback.
            raise LlmError(f"LLM request timed out ({type(exc).__name__})") from exc
        except httpx.HTTPStatusError as exc:
            # The start of the body often holds the server's explanation (e.g. "reasoning_effort not supported").
            # It comes from an external server and ends up in logs: cleaned and truncated.
            detail = clean_text(exc.response.text, 200) or "no details"
            raise LlmError(f"LLM server returned HTTP {exc.response.status_code}: {detail}") from exc
        except httpx.RequestError as exc:
            # Every other transport error: server down, unknown host, connection reset...
            raise LlmError(f"Could not reach LLM server ({type(exc).__name__})") from exc

        # --- 2. Decode the JSON ---
        try:
            data = response.json()
        except ValueError as exc:  # JSONDecodeError is a subclass of ValueError.
            raise LlmError("LLM response is not valid JSON") from exc

        # --- 3. Extract the text: choices[0].message.content ---
        try:
            choice = data["choices"][0]
            message = choice["message"]
            # Never sent tools, so a tool call can only mean a misbehaving server or model: refuse it.
            if message.get("tool_calls") or message.get("function_call"):
                raise LlmError("LLM answered with a tool call, but no tools are allowed")
            content = message["content"]
            # Why the model stopped: "stop" (normal end), "length" (max_tokens reached)...
            finish_reason = choice.get("finish_reason")
        # KeyError: a key is missing; IndexError: "choices" is empty;
        # TypeError / AttributeError: wrong type somewhere (e.g. the body is a list, a choice is a string).
        except (KeyError, IndexError, TypeError, AttributeError) as exc:
            raise LlmError("LLM response has an unexpected structure") from exc

        # Cut off by max_tokens: a truncated summary or an incomplete JSON is not an answer.
        if finish_reason == "length":
            raise LlmError("LLM response was cut off (max_tokens reached)")

        # Some servers send None as content, e.g. when generation was interrupted.
        if not isinstance(content, str):
            raise LlmError(f"LLM response content is not text (got {type(content).__name__})")

        # Some models write their reasoning into the answer, between <think> and </think>: remove it.
        content = _THINK_BLOCK.sub("", content).strip()

        # A remaining <think> means the reasoning was never closed: this is not an answer.
        if "<think>" in content:
            raise LlmError("LLM response contains an unfinished <think> block")

        # Security rule: an empty answer is rejected, never guessed.
        if not content:
            raise LlmError("LLM returned an empty response")

        # --- 4. Log duration and tokens: never the key, never the prompts (they contain the profile) ---
        usage = data.get("usage") or {}  # Optional, depending on the server.
        logger.debug(
            "LLM call: model=%s duration=%.2fs prompt_tokens=%s completion_tokens=%s",
            self._model,
            time.perf_counter() - started,
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
        )
        return content

    def _build_body(self, messages: list[Message], options: dict[str, Any]) -> dict[str, Any]:
        """Assemble the JSON request body: model + messages + reasoning_effort + options."""
        forbidden = _FORBIDDEN_KEYS & options.keys()
        if forbidden:
            raise TypeError(f"Tools are not allowed: the LLM must not be able to trigger actions {sorted(forbidden)}")
        conflicts = _RESERVED_KEYS & options.keys()
        if conflicts:
            raise TypeError(f"Reserved options, managed by the client: {sorted(conflicts)}")

        body: dict[str, Any] = {
            "model": self._model,
            # Copy each message: the client never modifies the caller's list.
            "messages": [dict(message) for message in messages],
        }
        # Only sent when set in the environment (LLM_REASONING_EFFORT).
        if self._reasoning_effort:
            body["reasoning_effort"] = self._reasoning_effort

        # Added last: a caller's option overrides the settings' default
        # (e.g. reasoning_effort="low" for a task that needs to think).
        body.update(options)

        # None means "do not send this field": never send null, the server could reject it.
        # e.g. chat(..., reasoning_effort=None) drops the settings' reasoning_effort for this call.
        return {key: value for key, value in body.items() if value is not None}

    def close(self) -> None:
        """Release the connection. chat() cannot be used afterwards."""
        # Without this, pooled connections stay open until the program ends
        # (and Python may warn about an unclosed resource).
        self._http_client.close()

    def __enter__(self) -> "LlmClient":
        """Start of `with LlmClient(...) as llm:`; `llm` is the client itself."""
        return self

    def __exit__(self, *exc_info: object) -> None:
        """End of the `with` block, even after an exception."""
        # Close in every case. Returning None (not True) lets the exception propagate:
        # clean up without hiding it.
        self.close()
