"""Tests to write for LlmClient. Each one is skipped until you implement it: remove the skip line.

No real LLM here: build the client with `transport=httpx.MockTransport(handler)`, where `handler`
receives the httpx.Request (you can inspect it) and returns an httpx.Response you choose.
See tests/conftest.py (FakeHttp) for an example of such a handler.
Useful: `json.loads(request.content)` gives the body the client sent.
"""

import pytest

TODO = pytest.mark.skip(reason="TODO: to write with the LlmClient implementation")


# --- Request: what the client sends ---


@TODO
def test_posts_to_chat_completions_under_the_base_url():
    """URL is {base_url}/chat/completions, method POST."""


@TODO
def test_body_contains_model_and_messages():
    """The model comes from the settings, the messages from the call."""


@TODO
def test_options_are_added_to_the_body():
    """e.g. chat(messages, temperature=0) -> "temperature": 0 in the body."""


@TODO
def test_authorization_header_only_with_an_api_key():
    """Key set -> "Bearer <key>". No key (local model) -> no Authorization header at all."""


# --- Response: what the client returns ---


@TODO
def test_returns_the_answer_text():
    """choices[0].message.content is returned as is."""


@TODO
def test_unexpected_response_shapes_raise_llm_error():
    """Parametrize: {}, {"choices": []}, {"choices": [{}]}, content None, body that is not JSON."""


@TODO
def test_blank_answer_raises_llm_error():
    """"" and "   " are not valid answers."""


# --- Errors ---


@TODO
def test_http_error_status_raises_llm_error():
    """e.g. 401 (bad key), 429 (rate limit), 500. The original error is kept as __cause__."""


@TODO
def test_network_error_raises_llm_error():
    """The handler can raise httpx.ConnectError or httpx.ReadTimeout."""


# --- Lifecycle and secrets ---


@TODO
def test_with_block_returns_the_client_and_closes_it():
    """`with LlmClient(...) as llm` gives a usable client; after the block it is closed."""


@TODO
def test_api_key_never_appears_in_logs(caplog):
    """Make a call that fails and one that succeeds with logging at DEBUG: the key is nowhere in caplog.text."""
