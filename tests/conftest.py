"""Fixtures shared by every test. Tests never touch the network or the real data/ folder."""

import json
from typing import Any

import httpx
import pytest

from tech_radar_agent.collectors import base, github, hackernews, rss

# Every module that opens an HTTP client: `fake_http` replaces the client in each of them.
COLLECTOR_MODULES = (github, hackernews, rss)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if a test tries a real HTTP request (httpx.MockTransport is not affected)."""

    def refuse(self: httpx.HTTPTransport, request: httpx.Request) -> httpx.Response:
        raise RuntimeError(f"Real network access in a test: {request.url}")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)


class FakeHttp:
    """Fake web server. Register responses in `routes`, read what was asked in `requests`.

    Route values: dict/list/None -> JSON, str/bytes -> raw body, int -> empty response with that
    status, httpx.Response -> returned as is, Exception -> raised (e.g. httpx.ConnectError).
    A URL matches its route exactly, or by scheme + host + path if the route has no query string.
    Unknown URLs get a 404.
    """

    def __init__(self) -> None:
        self.routes: dict[str, Any] = {}
        self.requests: list[httpx.Request] = []
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        without_query = str(request.url.copy_with(query=None))
        if url in self.routes:
            value = self.routes[url]
        elif without_query in self.routes:
            value = self.routes[without_query]
        else:
            return httpx.Response(404)

        if isinstance(value, Exception):
            raise value
        if isinstance(value, httpx.Response):
            return value
        if isinstance(value, int):
            return httpx.Response(value)
        if isinstance(value, (str, bytes)):
            return httpx.Response(200, content=value)
        return httpx.Response(200, content=json.dumps(value))

    def requested_urls(self) -> list[str]:
        return [str(request.url) for request in self.requests]


@pytest.fixture
def fake_http(monkeypatch: pytest.MonkeyPatch) -> FakeHttp:
    """Route every collector's HTTP traffic to a FakeHttp. Keeps the real client settings."""
    fake = FakeHttp()
    for module in COLLECTOR_MODULES:
        monkeypatch.setattr(module, "http_client", lambda: base.http_client(transport=fake.transport))
    return fake
