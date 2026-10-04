"""Tests for LlmClient. No real LLM: the network layer is an httpx.MockTransport (see FakeLlm)."""

import json
import logging
from typing import Any

import httpx
import pytest

from tech_radar_agent.llm import LlmSettings
from tech_radar_agent.llm.client import LlmClient, LlmError

BASE_URL = "https://api.example.com/v1"
MESSAGES = [{"role": "system", "content": "You rate articles."}, {"role": "user", "content": "Rate this."}]


def answer(content: Any = "The answer", finish_reason: str | None = "stop") -> dict:
    """A chat completions response body, as an OpenAI-compatible server sends it."""
    choice: dict[str, Any] = {"index": 0, "message": {"role": "assistant", "content": content}}
    if finish_reason is not None:
        choice["finish_reason"] = finish_reason
    return {"choices": [choice], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}


class FakeLlm:
    """Fake LLM server: records each request and replies with `reply` (dict -> JSON, Response, or Exception)."""

    def __init__(self) -> None:
        self.reply: Any = answer()
        self.requests: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if isinstance(self.reply, Exception):
            raise self.reply
        if isinstance(self.reply, httpx.Response):
            return self.reply
        return httpx.Response(200, json=self.reply)

    @property
    def last_body(self) -> dict:
        return json.loads(self.requests[-1].content)

    def client(self, **settings: Any) -> LlmClient:
        """An LlmClient wired to this fake server. Keyword arguments override the default settings."""
        values = {"base_url": BASE_URL, "model": "test-model"} | settings
        return LlmClient(LlmSettings(**values), transport=httpx.MockTransport(self.handle))


@pytest.fixture
def server() -> FakeLlm:
    return FakeLlm()


# --- Request: what the client sends ---


def test_posts_to_chat_completions_under_the_base_url(server):
    server.client().chat(MESSAGES)
    request = server.requests[0]
    assert request.method == "POST"
    assert str(request.url) == f"{BASE_URL}/chat/completions"


def test_body_contains_model_and_messages(server):
    server.client().chat(MESSAGES)
    assert server.last_body == {"model": "test-model", "messages": MESSAGES}


def test_messages_of_the_caller_are_not_modified(server):
    messages = [{"role": "user", "content": "Hi"}]
    server.client().chat(messages)
    assert messages == [{"role": "user", "content": "Hi"}]


def test_options_are_added_to_the_body(server):
    server.client().chat(MESSAGES, temperature=0, max_tokens=200)
    assert server.last_body["temperature"] == 0
    assert server.last_body["max_tokens"] == 200


def test_reasoning_effort_is_sent_only_when_set(server):
    server.client(reasoning_effort="none").chat(MESSAGES)
    assert server.last_body["reasoning_effort"] == "none"

    server.client(reasoning_effort=None).chat(MESSAGES)
    assert "reasoning_effort" not in server.last_body


def test_caller_option_overrides_the_settings(server):
    server.client(reasoning_effort="none").chat(MESSAGES, reasoning_effort="low")
    assert server.last_body["reasoning_effort"] == "low"


def test_timeout_comes_from_the_settings(server):
    client = server.client(request_timeout=12.5)
    assert client._http_client.timeout.read == 12.5
    assert client._http_client.timeout.connect == 12.5


@pytest.mark.parametrize(("api_key", "expected"), [("sk-secret", "Bearer sk-secret"), (None, None)])
def test_authorization_header_only_with_an_api_key(server, api_key, expected):
    server.client(api_key=api_key).chat(MESSAGES)
    assert server.requests[0].headers.get("Authorization") == expected


def test_none_options_are_not_sent(server):
    server.client(reasoning_effort="none").chat(MESSAGES, reasoning_effort=None, temperature=None)
    assert "reasoning_effort" not in server.last_body
    assert "temperature" not in server.last_body


@pytest.mark.parametrize("option", ["model", "messages"])
def test_reserved_options_raise_type_error(server, option):
    with pytest.raises(TypeError, match=option):
        server.client().chat(MESSAGES, **{option: "x"})
    assert server.requests == []  # Refused before anything is sent.


@pytest.mark.parametrize("option", ["tools", "tool_choice", "parallel_tool_calls", "functions", "function_call"])
def test_tools_can_never_be_offered_to_the_llm(server, option):
    # Security rule: the LLM gets no tools, so it can never ask this program to run anything.
    with pytest.raises(TypeError, match="Tools are not allowed"):
        server.client().chat(MESSAGES, **{option: [{"type": "function", "function": {"name": "run_shell"}}]})
    assert server.requests == []  # Refused before anything is sent.


def test_requests_never_contain_tools(server):
    server.client().chat(MESSAGES, temperature=0)
    assert not {"tools", "tool_choice", "functions"} & server.last_body.keys()


@pytest.mark.parametrize(
    "message",
    [
        pytest.param(
            {"role": "assistant", "content": None, "tool_calls": [{"type": "function", "function": {"name": "rm"}}]},
            id="tool-calls",
        ),
        pytest.param(
            {"role": "assistant", "content": "ok", "tool_calls": [{"type": "function", "function": {"name": "rm"}}]},
            id="tool-calls-with-text",
        ),
        pytest.param({"role": "assistant", "content": None, "function_call": {"name": "rm"}}, id="legacy-function-call"),
    ],
)
def test_tool_call_answers_are_refused(server, message):
    server.reply = {"choices": [{"message": message, "finish_reason": "tool_calls"}]}
    with pytest.raises(LlmError, match="tool call"):
        server.client().chat(MESSAGES)


# --- Response: what the client returns ---


def test_returns_the_answer_text(server):
    server.reply = answer("  A relevant article.\n")
    assert server.client().chat(MESSAGES) == "A relevant article."


def test_answer_without_finish_reason_is_accepted(server):
    # Some servers do not send finish_reason: that alone is not an error.
    server.reply = answer("Fine", finish_reason=None)
    assert server.client().chat(MESSAGES) == "Fine"


@pytest.mark.parametrize(
    "reply",
    [
        pytest.param({}, id="no-choices"),
        pytest.param({"choices": []}, id="empty-choices"),
        pytest.param({"choices": None}, id="choices-none"),
        pytest.param({"choices": [{}]}, id="no-message"),
        pytest.param({"choices": ["text"]}, id="choice-not-an-object"),
        pytest.param({"choices": [{"message": {}}]}, id="no-content"),
        pytest.param([1, 2], id="body-is-a-list"),
        pytest.param(answer(None), id="content-none"),
        pytest.param(answer(42), id="content-not-text"),
        pytest.param(httpx.Response(200, content=b"<html>Not JSON</html>"), id="not-json"),
    ],
)
def test_unexpected_response_shapes_raise_llm_error(server, reply):
    server.reply = reply
    with pytest.raises(LlmError):
        server.client().chat(MESSAGES)


def test_cut_off_answer_raises_llm_error(server):
    server.reply = answer("A summary that stops in the mid", finish_reason="length")
    with pytest.raises(LlmError, match="cut off"):
        server.client().chat(MESSAGES)


def test_think_block_is_removed(server):
    server.reply = answer("<think>Let me think\nabout it.</think>\n\nAnswer")
    assert server.client().chat(MESSAGES) == "Answer"


@pytest.mark.parametrize(
    "content",
    [
        pytest.param("<think>Still thinking when max_tokens hit", id="unclosed"),
        pytest.param("<think>only thoughts</think>", id="nothing-after-thinking"),
    ],
)
def test_think_block_without_answer_raises_llm_error(server, content):
    server.reply = answer(content)
    with pytest.raises(LlmError):
        server.client().chat(MESSAGES)


@pytest.mark.parametrize("content", ["", "   ", "\n\t"])
def test_blank_answer_raises_llm_error(server, content):
    server.reply = answer(content)
    with pytest.raises(LlmError, match="empty"):
        server.client().chat(MESSAGES)


# --- Errors ---


@pytest.mark.parametrize("status", [400, 401, 404, 429, 500, 503])
def test_http_error_status_raises_llm_error(server, status):
    server.reply = httpx.Response(status, json={"error": {"message": "Something went wrong"}})
    with pytest.raises(LlmError, match=f"HTTP {status}") as error:
        server.client().chat(MESSAGES)
    assert isinstance(error.value.__cause__, httpx.HTTPStatusError)
    assert "Something went wrong" in str(error.value)  # The server's explanation is kept.


def test_redirect_is_not_followed(server):
    server.reply = httpx.Response(301, headers={"Location": "http://elsewhere.example.com/v1/chat/completions"})
    with pytest.raises(LlmError, match="HTTP 301"):
        server.client().chat(MESSAGES)
    assert len(server.requests) == 1  # The new location was never requested.


def test_error_detail_is_cleaned_and_truncated(server):
    server.reply = httpx.Response(400, text="bad​ field\nFAKE LOG LINE " + "x" * 1000)
    with pytest.raises(LlmError) as error:
        server.client().chat(MESSAGES)
    message = str(error.value)
    assert "\n" not in message
    assert "​" not in message
    assert len(message) < 300


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        (httpx.ConnectError("Connection refused"), "Could not reach"),
        (httpx.ReadTimeout("Too slow"), "timed out"),
        (httpx.ConnectTimeout("Too slow"), "timed out"),
    ],
)
def test_network_error_raises_llm_error(server, failure, message):
    server.reply = failure
    with pytest.raises(LlmError, match=message) as error:
        server.client().chat(MESSAGES)
    assert error.value.__cause__ is failure


# --- Lifecycle and secrets ---


def test_with_block_returns_the_client_and_closes_it(server):
    with server.client() as llm:
        assert isinstance(llm, LlmClient)
        assert llm.chat(MESSAGES) == "The answer"
    assert llm._http_client.is_closed


def test_with_block_closes_even_after_an_error_and_does_not_hide_it(server):
    with pytest.raises(ValueError, match="boom"):
        with server.client() as llm:
            raise ValueError("boom")
    assert llm._http_client.is_closed


def test_api_key_never_appears_in_logs(server, caplog):
    caplog.set_level(logging.DEBUG)
    client = server.client(api_key="sk-super-secret")

    client.chat(MESSAGES)  # A successful call (logs at DEBUG).
    server.reply = httpx.Response(401, json={"error": "invalid key"})
    with pytest.raises(LlmError) as error:  # A failing call.
        client.chat(MESSAGES)

    assert "LLM call" in caplog.text  # Something was logged, so the check below means something.
    assert "sk-super-secret" not in caplog.text
    assert "sk-super-secret" not in str(error.value)
    assert "sk-super-secret" not in repr(client.__dict__)
