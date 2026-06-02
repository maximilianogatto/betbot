"""Lightweight pure-HTTP client for isolated FootyStats research.

The client deliberately keeps the public website and official paid API
separate. Public pages are useful for discovery and feasibility analysis, but
production integration should prefer the official API when an API key exists.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import logging
import time
from typing import Any
from urllib.parse import urljoin

import httpx

from sandbox.footystats_http.normalizers import (
    LiveScore,
    discover_league_links,
    parse_live_scores,
)


LOGGER = logging.getLogger(__name__)
PUBLIC_BASE_URL = "https://footystats.org/"
OFFICIAL_API_BASE_URL = "https://api.football-data-api.com/"


@dataclass(frozen=True)
class RequestMetric:
    """Timing and response-size evidence for one HTTP request."""

    method: str
    url: str
    status: int
    elapsed_ms: float
    body_size_bytes: int
    content_type: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize this metric for compact research reports."""

        return asdict(self)


class FootyStatsHTTPClient:
    """Fetch FootyStats data without Playwright.

    Args:
        timeout: Request timeout in seconds.
        retries: Number of additional attempts for transient failures.
        api_key: Optional official Football Data API key. It is never inferred
            from public pages and never required for public HTML or AJAX.
        transport: Optional injected ``httpx`` transport for unit tests.
    """

    def __init__(
        self,
        *,
        timeout: float = 20.0,
        retries: int = 2,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.timeout = timeout
        self.retries = retries
        self.api_key = api_key
        self.metrics: list[RequestMetric] = []
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )

    def __enter__(self) -> FootyStatsHTTPClient:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def close(self) -> None:
        """Release pooled HTTP connections."""

        self._client.close()

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        """Issue one retried HTTP request and record compact metrics."""

        for attempt in range(self.retries + 1):
            started_at = time.monotonic()
            response = self._client.request(method, url, **kwargs)
            metric = RequestMetric(
                method=method.upper(),
                url=str(response.url),
                status=response.status_code,
                elapsed_ms=round((time.monotonic() - started_at) * 1000, 3),
                body_size_bytes=len(response.content),
                content_type=response.headers.get("content-type", ""),
            )
            self.metrics.append(metric)
            LOGGER.info(
                "FootyStats HTTP request method=%s status=%s duration_ms=%.3f bytes=%s url=%s",
                metric.method,
                metric.status,
                metric.elapsed_ms,
                metric.body_size_bytes,
                metric.url,
            )
            if response.status_code not in {429, 500, 502, 503, 504} or attempt >= self.retries:
                response.raise_for_status()
                return response
            time.sleep(min(0.5 * (2**attempt), 2.0))
        raise RuntimeError("Unreachable retry loop")

    def fetch_public_page(self, path_or_url: str = "/") -> str:
        """Fetch one public HTML page using plain HTTP."""

        url = urljoin(PUBLIC_BASE_URL, path_or_url)
        return self.request("GET", url).text

    def discover_leagues(self) -> list[dict[str, str]]:
        """Discover country -> league page links from public homepage HTML."""

        return [item.to_dict() for item in discover_league_links(self.fetch_public_page("/"))]

    def fetch_league_page(self, country_slug: str, league_slug: str) -> str:
        """Fetch one public league page by stable slugs."""

        return self.fetch_public_page(f"/{country_slug}/{league_slug}")

    def fetch_match_page(self, match_path: str) -> str:
        """Fetch one public match H2H page path."""

        return self.fetch_public_page(match_path)

    def fetch_live_scores(self) -> list[LiveScore]:
        """Fetch the public low-cost live-score JSON feed."""

        response = self.request("GET", urljoin(PUBLIC_BASE_URL, "/ajax_livescore.php"))
        return parse_live_scores(response.json())

    def fetch_live_match_panel(self, *, match_id: str, competition_id: str) -> str:
        """Fetch the HTML live panel for one match when FootyStats exposes it."""

        response = self.request(
            "POST",
            urljoin(PUBLIC_BASE_URL, "/ajax_livescore_h2h.php"),
            data={"ziz": match_id, "zizz": competition_id},
        )
        return response.text

    def official_api_request(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        api_key: str | None = None,
    ) -> Any:
        """Call one documented official JSON endpoint.

        A key must be supplied explicitly or configured on construction.
        ``key=example`` can be passed manually for documented demo datasets.
        """

        selected_key = api_key or self.api_key
        if not selected_key:
            raise ValueError("FootyStats official API requests require an explicit API key")
        query = {"key": selected_key, **(params or {})}
        response = self.request("GET", urljoin(OFFICIAL_API_BASE_URL, endpoint.lstrip("/")), params=query)
        return response.json()
