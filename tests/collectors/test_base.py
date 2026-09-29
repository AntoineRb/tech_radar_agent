import httpx
import pytest

from tech_radar_agent.collectors import base
from tech_radar_agent.collectors.base import (
    USER_AGENT,
    Collector,
    UnsafeResponseError,
    fetch,
    fetch_json,
    html_to_text,
    http_client,
)


@pytest.fixture
def client(fake_http):
    with http_client(transport=fake_http.transport) as client:
        yield client


class TestHttpClient:
    def test_shared_settings(self):
        with http_client() as client:
            assert client.headers["User-Agent"] == USER_AGENT
            assert client.timeout.read == 10
            assert client.follow_redirects


class TestFetch:
    def test_returns_body(self, fake_http, client):
        fake_http.routes["https://example.com/feed"] = b"hello"
        assert fetch(client, "https://example.com/feed") == b"hello"

    def test_json(self, fake_http, client):
        fake_http.routes["https://example.com/api"] = {"ids": [1, 2]}
        assert fetch_json(client, "https://example.com/api") == {"ids": [1, 2]}

    def test_http_is_refused_before_any_request(self, fake_http, client):
        with pytest.raises(UnsafeResponseError, match="non-HTTPS"):
            fetch(client, "http://example.com/feed")
        assert fake_http.requests == []

    def test_redirect_to_http_is_refused(self, fake_http, client):
        fake_http.routes["https://example.com/feed"] = httpx.Response(
            301, headers={"Location": "http://example.com/feed"}
        )
        fake_http.routes["http://example.com/feed"] = b"downgraded"
        with pytest.raises(UnsafeResponseError, match="Redirected"):
            fetch(client, "https://example.com/feed")

    def test_redirect_to_https_is_followed(self, fake_http, client):
        fake_http.routes["https://example.com/old"] = httpx.Response(
            301, headers={"Location": "https://example.com/new"}
        )
        fake_http.routes["https://example.com/new"] = b"moved"
        assert fetch(client, "https://example.com/old") == b"moved"

    def test_too_large_response_is_refused(self, fake_http, client, monkeypatch):
        monkeypatch.setattr(base, "MAX_RESPONSE_BYTES", 10)
        fake_http.routes["https://example.com/big"] = b"x" * 11
        with pytest.raises(UnsafeResponseError, match="larger than"):
            fetch(client, "https://example.com/big")

    def test_response_at_the_limit_is_accepted(self, fake_http, client, monkeypatch):
        monkeypatch.setattr(base, "MAX_RESPONSE_BYTES", 10)
        fake_http.routes["https://example.com/ok"] = b"x" * 10
        assert fetch(client, "https://example.com/ok") == b"x" * 10

    def test_error_status_raises(self, fake_http, client):
        fake_http.routes["https://example.com/down"] = 503
        with pytest.raises(httpx.HTTPStatusError):
            fetch(client, "https://example.com/down")

    def test_unsafe_response_is_an_http_error(self):
        # Collectors catch httpx.HTTPError to skip a failing item: this must include our refusals.
        assert issubclass(UnsafeResponseError, httpx.HTTPError)


class TestHtmlToText:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (None, None),
            ("", None),
            ("<p></p>", None),
            ("plain text", "plain text"),
            ("<p>Hello <b>world</b></p>", "Hello world"),
            ("<p>one</p><p>two</p>", "one two"),
            ("Fish &amp; chips &lt;3", "Fish & chips <3"),
            ("<a href='https://x.com'>link</a>", "link"),
        ],
    )
    def test_conversion(self, value, expected):
        assert html_to_text(value) == expected


class TestCollector:
    class Dummy(Collector):
        type = "dummy"

        def collect(self):
            return []

    def test_name_defaults_to_type(self):
        assert self.Dummy().name == "dummy"

    def test_custom_name(self):
        assert self.Dummy(name="my-source").name == "my-source"

    def test_collect_is_required(self):
        class Incomplete(Collector):
            type = "incomplete"

        with pytest.raises(TypeError):
            Incomplete()
