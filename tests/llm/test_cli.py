"""Tests for `python -m tech_radar_agent.llm` (the setup check command). No real LLM."""

import json

import httpx
import pytest

from tech_radar_agent.llm import __main__ as cli
from tech_radar_agent.llm.client import LlmClient


@pytest.fixture
def llm_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://api.example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_API_KEY", "sk-secret")


def use_fake_server(monkeypatch, handler) -> list[httpx.Request]:
    """Make the command's LlmClient talk to `handler` instead of the network."""
    requests: list[httpx.Request] = []

    def recording_handler(request):
        requests.append(request)
        return handler(request)

    monkeypatch.setattr(
        cli, "LlmClient", lambda settings: LlmClient(settings, transport=httpx.MockTransport(recording_handler))
    )
    return requests


def reply(content):
    return lambda request: httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_prints_the_answer(llm_env, monkeypatch, capsys):
    requests = use_fake_server(monkeypatch, reply("pong"))
    assert cli.main(["Say pong"]) == 0

    out, err = capsys.readouterr()
    assert out == "pong\n"
    assert "test-model" in err
    assert json.loads(requests[0].content)["messages"] == [{"role": "user", "content": "Say pong"}]


def test_default_prompt(llm_env, monkeypatch, capsys):
    requests = use_fake_server(monkeypatch, reply("pong"))
    cli.main([])
    assert json.loads(requests[0].content)["messages"][0]["content"] == cli.DEFAULT_PROMPT


def test_llm_failure(llm_env, monkeypatch, capsys):
    use_fake_server(monkeypatch, lambda request: httpx.Response(401, json={"error": "invalid key"}))
    assert cli.main([]) == 1
    assert "LLM error: LLM server returned HTTP 401" in capsys.readouterr().err


def test_invalid_settings(monkeypatch, capsys):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert cli.main([]) == 2
    assert "Invalid LLM settings" in capsys.readouterr().err


def test_api_key_is_never_printed(llm_env, monkeypatch, capsys):
    use_fake_server(monkeypatch, reply("pong"))
    cli.main(["--debug", "hi"])
    out, err = capsys.readouterr()
    assert "sk-secret" not in out + err
