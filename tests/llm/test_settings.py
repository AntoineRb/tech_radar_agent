from pathlib import Path

import pytest

from tech_radar_agent.llm import LlmSettings, is_allowed_llm_url, load_llm_settings
from tech_radar_agent.llm.settings import DEFAULT_REQUEST_TIMEOUT, MAX_MIN_INTERVAL

ENV_EXAMPLE = Path(__file__).parents[2] / ".env.example"
LOCAL = {"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "m"}


class TestLoad:
    def test_local(self):
        settings = load_llm_settings({"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "qwen3:4b"})
        assert settings == LlmSettings(base_url="http://localhost:11434/v1", model="qwen3:4b", api_key=None)
        assert settings.is_local

    def test_remote(self):
        settings = load_llm_settings(
            {"LLM_BASE_URL": "https://api.example.com/v1", "LLM_MODEL": "m", "LLM_API_KEY": "secret"}
        )
        assert settings.api_key == "secret"
        assert not settings.is_local

    def test_values_are_trimmed(self):
        settings = load_llm_settings(
            {"LLM_BASE_URL": " https://api.example.com/v1/ ", "LLM_MODEL": " m ", "LLM_API_KEY": " k "}
        )
        assert (settings.base_url, settings.model, settings.api_key) == ("https://api.example.com/v1", "m", "k")

    def test_empty_key_means_no_key(self):
        settings = load_llm_settings({"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "m", "LLM_API_KEY": ""})
        assert settings.api_key is None

    @pytest.mark.parametrize(
        ("environ", "missing"),
        [
            ({}, "LLM_BASE_URL, LLM_MODEL"),
            ({"LLM_MODEL": "m"}, "LLM_BASE_URL"),
            ({"LLM_BASE_URL": "https://api.example.com/v1", "LLM_MODEL": "  "}, "LLM_MODEL"),
        ],
    )
    def test_missing_variables(self, environ, missing):
        with pytest.raises(ValueError, match=f"Missing environment variables: {missing}"):
            load_llm_settings(environ)

    def test_remote_http_is_refused(self):
        with pytest.raises(ValueError, match="https"):
            load_llm_settings({"LLM_BASE_URL": "http://api.example.com/v1", "LLM_MODEL": "m"})

    def test_optional_tuning_defaults(self):
        settings = load_llm_settings({"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "m"})
        assert settings.reasoning_effort is None
        assert settings.request_timeout == DEFAULT_REQUEST_TIMEOUT

    def test_optional_tuning_from_environment(self):
        settings = load_llm_settings(
            {
                "LLM_BASE_URL": "http://localhost:11434/v1",
                "LLM_MODEL": "m",
                "LLM_REASONING_EFFORT": " none ",
                "LLM_REQUEST_TIMEOUT": "2.5",
            }
        )
        assert settings.reasoning_effort == "none"
        assert settings.request_timeout == 2.5

    @pytest.mark.parametrize("value", ["", "   "])
    def test_empty_tuning_means_default(self, value):
        settings = load_llm_settings(
            {
                "LLM_BASE_URL": "http://localhost:11434/v1",
                "LLM_MODEL": "m",
                "LLM_REASONING_EFFORT": value,
                "LLM_REQUEST_TIMEOUT": value,
            }
        )
        assert settings.reasoning_effort is None
        assert settings.request_timeout == DEFAULT_REQUEST_TIMEOUT

    @pytest.mark.parametrize("value", ["abc", "30s", "0", "-5", "nan", "inf"])
    def test_invalid_timeout(self, value):
        with pytest.raises(ValueError, match="LLM_REQUEST_TIMEOUT"):
            load_llm_settings(
                {"LLM_BASE_URL": "http://localhost:11434/v1", "LLM_MODEL": "m", "LLM_REQUEST_TIMEOUT": value}
            )

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_no_min_interval_by_default(self, value):
        environ = LOCAL if value is None else LOCAL | {"LLM_MIN_INTERVAL_SECONDS": value}
        assert load_llm_settings(environ).min_interval == 0.0

    @pytest.mark.parametrize(
        ("value", "expected"),
        [("0", 0.0), ("6", 6.0), (" 4.5 ", 4.5), ("300", MAX_MIN_INTERVAL)],  # Both bounds included.
    )
    def test_min_interval_from_environment(self, value, expected):
        assert load_llm_settings(LOCAL | {"LLM_MIN_INTERVAL_SECONDS": value}).min_interval == expected

    @pytest.mark.parametrize(
        "value",
        [
            "abc",
            "6s",  # The unit is in the name, not the value.
            "-1",
            "300.01",
            "6000",  # Milliseconds by mistake: would wait 100 min per request.
            "nan",
            "inf",
            "-inf",
        ],
    )
    def test_invalid_min_interval(self, value):
        with pytest.raises(ValueError, match="LLM_MIN_INTERVAL_SECONDS"):
            load_llm_settings(LOCAL | {"LLM_MIN_INTERVAL_SECONDS": value})

    def test_reads_the_process_environment_by_default(self, monkeypatch):
        monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:11434/v1")
        monkeypatch.setenv("LLM_MODEL", "m")
        monkeypatch.delenv("LLM_API_KEY", raising=False)
        assert load_llm_settings().model == "m"


class TestSecrets:
    def test_api_key_is_never_printed(self):
        settings = LlmSettings(base_url="https://api.example.com/v1", model="m", api_key="super-secret")
        assert "super-secret" not in repr(settings)
        assert "super-secret" not in str(settings)

    def test_env_example_contains_no_real_key(self):
        values = dict(
            line.split("=", 1) for line in ENV_EXAMPLE.read_text().splitlines() if line.startswith("LLM_API_KEY=")
        )
        assert values == {"LLM_API_KEY": ""}

    def test_env_example_is_valid(self):
        environ = dict(
            line.split("=", 1)
            for line in ENV_EXAMPLE.read_text().splitlines()
            if line and not line.startswith("#")
        )
        settings = load_llm_settings(environ)
        assert settings.is_local
        assert settings.reasoning_effort == "none"
        assert settings.min_interval == 0.0  # No pacing for a local model.


class TestAllowedUrl:
    @pytest.mark.parametrize(
        "url",
        [
            "https://api.example.com/v1",
            "http://localhost:11434/v1",
            "http://127.0.0.1:11434/v1",
            "http://[::1]:11434/v1",
            "HTTP://LOCALHOST:11434/v1",
        ],
    )
    def test_allowed(self, url):
        assert is_allowed_llm_url(url)

    @pytest.mark.parametrize(
        "url",
        [
            "http://api.example.com/v1",  # Remote over plain http.
            "http://192.168.1.10:11434/v1",  # Another machine on the network is not "local".
            "http://localhost.evil.com/v1",  # Look-alike host.
            "http://evil.com@localhost.example/v1",
            "ftp://localhost/v1",
            "https://",
            "localhost:11434",
            "",
        ],
    )
    def test_refused(self, url):
        assert not is_allowed_llm_url(url)
