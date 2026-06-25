"""Minimal HTTP transport for public FootyStats pages and its licensed API."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import threading
import time
from typing import Any, Callable
from urllib.parse import urljoin

import httpx


logger = logging.getLogger(__name__)


class FootyStatsHTTPError(RuntimeError):
    """Raised when FootyStats returns an unusable HTTP response."""


@dataclass(frozen=True)
class FootyStatsHTTPSettings:
    """Configure conservative public-page HTTP access."""

    public_base_url: str = "https://footystats.org/"
    api_base_url: str = "https://api.football-data-api.com/"
    timeout_seconds: float = 20.0
    retries: int = 2
    retry_delay_seconds: float = 0.5
    min_request_interval_seconds: float = 0.2
    # Public HTML pages now sit behind a Cloudflare Managed Challenge, so they
    # are fetched through a headed browser instead of plain httpx. The compact
    # AJAX feeds (live scores) and the licensed API stay on httpx.
    browser_fetch_html: bool = True
    browser_fetch_timeout_seconds: float = 90.0


class FootyStatsHTTPClient:
    """Fetch FootyStats without browser headers, cookies or Playwright.

    Research showed that plain requests work while synthetic browser headers
    may trigger Cloudflare. The lock keeps the low-rate public fallback simple.
    """

    def __init__(
        self,
        settings: FootyStatsHTTPSettings | None = None,
        *,
        api_key: str | None = None,
        transport: httpx.BaseTransport | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or FootyStatsHTTPSettings()
        self.api_key = (api_key or "").strip() or None
        self._client = httpx.Client(
            timeout=self.settings.timeout_seconds,
            follow_redirects=True,
            transport=transport,
        )
        self._monotonic = monotonic
        self._sleep = sleep
        self._request_lock = threading.Lock()
        self._last_request_started_at: float | None = None
        self.request_count = 0
        # An injected transport means a test/offline stub; never spin up a real
        # browser in that case. Otherwise the headed-browser fallback is created
        # lazily on the first public-HTML fetch.
        self._browser_fetch_enabled = self.settings.browser_fetch_html and transport is None
        self._browser = None
        self._browser_lock = threading.Lock()

    def close(self) -> None:
        """Close pooled HTTP connections and the headed browser, if any."""

        self._client.close()
        browser = self._browser
        if browser is not None:
            browser.close()
            self._browser = None

    def get_public_html(self, path_or_url: str) -> str:
        """GET one public HTML page, clearing Cloudflare via a headed browser."""

        url = urljoin(self.settings.public_base_url, path_or_url)
        if self._browser_fetch_enabled:
            return self._browser_fetcher().fetch_html(
                url, timeout=self.settings.browser_fetch_timeout_seconds
            )
        return self._request_text(url)

    def _browser_fetcher(self):
        if self._browser is None:
            with self._browser_lock:
                if self._browser is None:
                    from stats_providers.footystats_http.cloudflare_browser import (
                        CloudflareBrowserFetcher,
                    )

                    self._browser = CloudflareBrowserFetcher()
        return self._browser

    def get_live_scores(self) -> list[dict[str, Any]]:
        """Return the compact undocumented live-score list when available."""

        response = self._request("GET", urljoin(self.settings.public_base_url, "/ajax_livescore.php"))
        try:
            payload = response.json()
        except ValueError as exc:
            raise FootyStatsHTTPError("FootyStats live-score feed returned invalid JSON.") from exc
        return [item for item in payload if isinstance(item, dict)] if isinstance(payload, list) else []

    def get_official_json(self, endpoint: str, **params: Any) -> Any:
        """GET one licensed official API endpoint when `FOOTYSTATS_API_KEY` exists."""

        if not self.api_key:
            raise FootyStatsHTTPError("FOOTYSTATS_API_KEY is required for the official FootyStats API.")
        response = self._request(
            "GET",
            urljoin(self.settings.api_base_url, endpoint.lstrip("/")),
            params={"key": self.api_key, **params},
        )
        try:
            return response.json()
        except ValueError as exc:
            raise FootyStatsHTTPError(f"Official FootyStats endpoint {endpoint} returned invalid JSON.") from exc

    def _request_text(self, url: str) -> str:
        response = self._request("GET", url)
        return response.text

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.settings.retries + 2):
            try:
                with self._request_lock:
                    self._wait_for_rate_limit()
                    started_at = self._monotonic()
                    self._last_request_started_at = started_at
                    response = self._client.request(method, url, **kwargs)
                    self.request_count += 1
                elapsed = self._monotonic() - started_at
                logger.debug(
                    "FootyStats HTTP request method=%s status=%s duration_seconds=%.3f url=%s",
                    method,
                    response.status_code,
                    elapsed,
                    response.url,
                )
                if response.status_code == 404:
                    return response
                response.raise_for_status()
                return response
            except httpx.HTTPError as exc:
                last_error = exc
                if attempt <= self.settings.retries:
                    self._sleep(self.settings.retry_delay_seconds * attempt)
        raise FootyStatsHTTPError(f"FootyStats request failed after retries: {last_error}") from last_error

    def _wait_for_rate_limit(self) -> None:
        if self._last_request_started_at is None:
            return
        remaining = self.settings.min_request_interval_seconds - (
            self._monotonic() - self._last_request_started_at
        )
        if remaining > 0:
            self._sleep(remaining)


__all__ = ["FootyStatsHTTPClient", "FootyStatsHTTPError", "FootyStatsHTTPSettings"]
