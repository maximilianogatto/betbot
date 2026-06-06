from __future__ import annotations

from typing import Any
import httpx

class SlovakSportnetHTTPClient:
    """HTTP client for Slovakia Sportnet API."""

    def __init__(self, *, timeout: float = 20.0, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> SlovakSportnetHTTPClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_part(self, competition_id: str, part_id: str) -> dict[str, Any]:
        url = f"https://sutaze.api.sportnet.online/api/v2/competitions/{competition_id}/parts/{part_id}"
        resp = self.client.get(url)
        resp.raise_for_status()
        return resp.json()

    def get_matches(self, competition_id: str, limit: int = 100) -> dict[str, Any]:
        url = "https://sutaze.api.sportnet.online/api/v1/matches"
        params = {"competitionId": competition_id, "limit": limit}
        resp = self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
