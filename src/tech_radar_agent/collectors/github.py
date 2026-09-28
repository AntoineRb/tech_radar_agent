import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from tech_radar_agent.collectors.base import Collector, fetch_json, http_client
from tech_radar_agent.models import Article

logger = logging.getLogger(__name__)

# https://docs.github.com/en/rest/search/search#search-repositories
SEARCH_URL = "https://api.github.com/search/repositories"
API_HEADERS = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
MAX_PER_PAGE = 100  # API limit for one page of results.


class GitHubCollector(Collector):
    """Recently created repositories with the most stars, via the GitHub Search API.

    GitHub has no official "trending" API: this is the closest reliable equivalent.
    Works without authentication (10 searches per minute). If the GITHUB_TOKEN environment
    variable is set (it is in GitHub Actions), it is used for a higher rate limit.
    """

    type = "github"

    def __init__(
        self,
        name: str | None = None,
        query: str = "",
        created_within_days: int = 7,
        min_stars: int = 50,
        limit: int = 30,
    ) -> None:
        super().__init__(name)
        if not 1 <= limit <= MAX_PER_PAGE:
            raise ValueError(f"GitHub limit must be between 1 and {MAX_PER_PAGE}, got {limit}")
        self.query = query  # Extra search qualifiers, e.g. "language:python" or "topic:llm".
        self.created_within_days = created_within_days
        self.min_stars = min_stars
        self.limit = limit

    def collect(self) -> list[Article]:
        with http_client() as client:
            client.headers.update(API_HEADERS)
            if token := os.environ.get("GITHUB_TOKEN"):
                client.headers["Authorization"] = f"Bearer {token}"
            results = fetch_json(client, self._search_url())

        articles = []
        for repo in results.get("items", []):
            try:
                articles.append(self._to_article(repo))
            except (KeyError, ValueError) as error:  # Missing field, or rejected by Article's checks.
                logger.warning("%s: skipping repo %r (%s)", self.name, repo.get("full_name"), error)

        logger.info("%s: %d articles from %d repos", self.name, len(articles), len(results.get("items", [])))
        return articles

    def _search_url(self) -> str:
        since = (datetime.now(timezone.utc) - timedelta(days=self.created_within_days)).date()
        query = f"created:>={since.isoformat()} stars:>={self.min_stars} {self.query}".strip()
        params = {"q": query, "sort": "stars", "order": "desc", "per_page": self.limit}
        return f"{SEARCH_URL}?{urlencode(params)}"

    def _to_article(self, repo: dict[str, Any]) -> Article:
        return Article(
            source=self.name,
            title=repo["full_name"],  # "owner/name"
            url=repo["html_url"],
            author=repo.get("owner", {}).get("login"),
            content=repo.get("description"),
            published_at=datetime.fromisoformat(repo["created_at"]) if repo.get("created_at") else None,
            extra={
                "stars": repo.get("stargazers_count", 0),
                "language": repo.get("language"),
                "topics": repo.get("topics", []),
            },
        )
