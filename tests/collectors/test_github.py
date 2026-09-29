from datetime import datetime, timedelta, timezone

import httpx
import pytest

from tech_radar_agent.collectors.github import SEARCH_URL, GitHubCollector


def repo(full_name: str = "alice/tool", **fields) -> dict:
    return {
        "full_name": full_name,
        "html_url": f"https://github.com/{full_name}",
        "owner": {"login": full_name.split("/")[0]},
        "description": "A useful tool",
        "created_at": "2026-09-25T10:00:00Z",
        "stargazers_count": 1234,
        "language": "Python",
        "topics": ["llm", "agents"],
    } | fields


def serve(fake_http, *repos: dict) -> None:
    fake_http.routes[SEARCH_URL] = {"total_count": len(repos), "items": list(repos)}


@pytest.fixture(autouse=True)
def no_token(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)


class TestMapping:
    def test_repository(self, fake_http):
        serve(fake_http, repo())
        [article] = GitHubCollector().collect()
        assert article.source == "github"
        assert article.title == "alice/tool"
        assert article.url == "https://github.com/alice/tool"
        assert article.author == "alice"
        assert article.content == "A useful tool"
        assert article.published_at == datetime(2026, 9, 25, 10, 0, tzinfo=timezone.utc)
        assert article.extra == {"stars": 1234, "language": "Python", "topics": ["llm", "agents"]}

    def test_optional_fields_can_be_missing(self, fake_http):
        serve(fake_http, repo(description=None, language=None, created_at=None, owner={}))
        [article] = GitHubCollector().collect()
        assert article.content is None
        assert article.author is None
        assert article.published_at is None

    def test_broken_repositories_are_skipped(self, fake_http):
        no_url = repo("bob/no-url")
        del no_url["html_url"]
        serve(fake_http, repo(), no_url, repo("eve/evil", html_url="javascript:alert(1)"))
        assert [a.title for a in GitHubCollector().collect()] == ["alice/tool"]

    def test_empty_results(self, fake_http):
        serve(fake_http)
        assert GitHubCollector().collect() == []


class TestSearchQuery:
    def test_query_parameters(self, fake_http):
        serve(fake_http)
        GitHubCollector(query="language:python", created_within_days=3, min_stars=10, limit=5).collect()

        params = fake_http.requests[0].url.params
        since = (datetime.now(timezone.utc) - timedelta(days=3)).date().isoformat()
        assert params["q"] == f"created:>={since} stars:>=10 language:python"
        assert params["sort"] == "stars"
        assert params["order"] == "desc"
        assert params["per_page"] == "5"

    def test_no_extra_query(self, fake_http):
        serve(fake_http)
        GitHubCollector().collect()
        assert fake_http.requests[0].url.params["q"].endswith("stars:>=50")

    @pytest.mark.parametrize("limit", [0, 101])
    def test_limit_must_fit_one_page(self, limit):
        with pytest.raises(ValueError, match="between 1 and 100"):
            GitHubCollector(limit=limit)


class TestAuthentication:
    def test_api_headers(self, fake_http):
        serve(fake_http)
        GitHubCollector().collect()
        headers = fake_http.requests[0].headers
        assert headers["Accept"] == "application/vnd.github+json"
        assert headers["X-GitHub-Api-Version"] == "2022-11-28"

    def test_no_token_no_authorization(self, fake_http):
        serve(fake_http)
        GitHubCollector().collect()
        assert "Authorization" not in fake_http.requests[0].headers

    def test_token_from_environment(self, fake_http, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "secret-token")
        serve(fake_http)
        GitHubCollector().collect()
        assert fake_http.requests[0].headers["Authorization"] == "Bearer secret-token"


class TestErrors:
    def test_rate_limited_raises(self, fake_http):
        fake_http.routes[SEARCH_URL] = 403
        with pytest.raises(httpx.HTTPStatusError):
            GitHubCollector().collect()
