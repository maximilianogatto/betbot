from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx

from sandbox.sportradar_stats.http_research.core import (
    extract_gismo_endpoint_key,
    replace_endpoint_path_in_signed_url,
    safe_json_loads,
)


DEFAULT_HEADERS = {
    "accept": "application/json,text/plain,*/*",
    "origin": "https://statshub.sportradar.com",
    "referer": "https://statshub.sportradar.com/",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}


class StatshubHttpResearchClient:
    """Experimental client that replays captured Statshub signed URLs.

    This is intentionally a research adapter, not production code. Direct page
    methods use regular HTTP; gismo methods require a previous capture unless a
    future experiment discovers a signer/bootstrap endpoint.
    """

    def __init__(
        self,
        *,
        capture_dir: Path | None = None,
        timeout_seconds: float = 20.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.capture_dir = capture_dir
        self.timeout_seconds = timeout_seconds
        self.headers = {**DEFAULT_HEADERS, **(headers or {})}
        self._records = self._load_records(capture_dir) if capture_dir else []

    def fetch_sport(self, sport_id: int | str = 1) -> dict[str, Any]:
        return self._fetch_document(f"https://statshub.sportradar.com/bet365/en/sport/{sport_id}")

    def fetch_tournament(self, tournament_id: int | str, *, sport_id: int | str = 1) -> dict[str, Any]:
        return self._fetch_document(
            f"https://statshub.sportradar.com/bet365/en/sport/{sport_id}/tournament/{tournament_id}"
        )

    def fetch_tournament_fixtures(self, tournament_id: int | str, *, sport_id: int | str = 1) -> dict[str, Any]:
        return self._fetch_document(
            f"https://statshub.sportradar.com/bet365/en/sport/{sport_id}/tournament/{tournament_id}/fixtures?view=round"
        )

    def fetch_match(self, match_id: int | str, *, host: str = "statshub.sportradar.com") -> dict[str, Any]:
        return self._fetch_document(f"https://{host}/bet365/en/match/{match_id}")

    def fetch_endpoint_from_captured_url(self, url: str) -> dict[str, Any]:
        with httpx.Client(headers=self.headers, timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
        return self._response_payload(response)

    def replay_endpoint(self, endpoint_key: str, ids: list[int | str] | tuple[int | str, ...]) -> dict[str, Any]:
        sample = self._find_sample_for(endpoint_key)
        if sample is None:
            raise ValueError(f"No captured signed URL available for endpoint {endpoint_key!r}.")
        path = "/".join([endpoint_key, *[str(item) for item in ids]])
        url = replace_endpoint_path_in_signed_url(str(sample["url"]), path)
        return self.fetch_endpoint_from_captured_url(url)

    def _fetch_document(self, url: str) -> dict[str, Any]:
        with httpx.Client(headers=self.headers, timeout=self.timeout_seconds, follow_redirects=True) as client:
            response = client.get(url)
        return self._response_payload(response)

    def _response_payload(self, response: httpx.Response) -> dict[str, Any]:
        text = response.text
        body_json = safe_json_loads(text)
        return {
            "url": str(response.url),
            "status": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body_json": body_json,
            "preview": None if body_json is not None else text[:1000],
            "endpoint_key": extract_gismo_endpoint_key(str(response.url), body_json),
        }

    def _find_sample_for(self, endpoint_key: str) -> dict[str, Any] | None:
        for record in self._records:
            if str(record.get("endpoint_key") or "") == endpoint_key and record.get("has_signed_token"):
                return record
        return None

    @staticmethod
    def _load_records(capture_dir: Path | None) -> list[dict[str, Any]]:
        if capture_dir is None:
            return []
        path = capture_dir / "fetch_only.ndjson"
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    records.append(payload)
        return records
