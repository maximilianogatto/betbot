from __future__ import annotations

from typing import Any
import httpx

class RomaniaFRFHTTPClient:
    """HTTP client for Romania FRF Datalake API."""

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
        self.token: str | None = None

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> RomaniaFRFHTTPClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_token(self) -> str:
        url = "https://api.datalake.frf.ro/Auth/GetToken"
        credentials = {
            "apiUser": "HaiLaFotbal",
            "apiPassword": "g2NmJb'{C/x#DqU[8cn57u"
        }
        resp = self.client.post(url, json=credentials)
        resp.raise_for_status()
        token = resp.json().get("token")
        if not token:
            raise RuntimeError("No token returned by FRF auth API")
        return str(token)

    def _get_headers(self) -> dict[str, str]:
        if not self.token:
            self.token = self.get_token()
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def get_filters(self, tour_round_id: int = 43614) -> dict[str, Any]:
        url = "https://api.datalake.frf.ro/HaiLaFotbal/GetFRFFilters"
        resp = self.client.post(url, json={"TourRoundId": tour_round_id}, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()

    def get_matches(self, season_id: int, stage_id: int, series_id: int, tour_round_id: int) -> dict[str, Any]:
        url = "https://api.datalake.frf.ro/HaiLaFotbal/GetFRFMatches"
        payload = {
            "seasonId": season_id,
            "stageId": stage_id,
            "seriesId": series_id,
            "tourRoundId": tour_round_id
        }
        resp = self.client.post(url, json=payload, headers=self._get_headers())
        resp.raise_for_status()
        return resp.json()
