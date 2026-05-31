"""Async HTTP client for the Rainbet/Betby (sptpub) prematch snapshot feed.

Flow (all plain HTTP, no token):
  1. GET ``.../<lang>/0`` -> a manifest with ``version``, ``top_events_versions``
     and ``rest_events_versions``.
  2. GET ``.../<lang>/<chunk_version>`` for each advertised version.
  3. Deep-merge the chunks into one snapshot with ``sports``, ``categories``,
     ``tournaments`` and ``events``.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from extractors.rainbet_http.settings import RainbetHttpSettings

logger = logging.getLogger(__name__)


class RainbetHttpClient:
    """Defensive async client for the Betby sptpub snapshot endpoints."""

    def __init__(self, settings: RainbetHttpSettings) -> None:
        if not settings.api_host or not settings.brand_id:
            raise ValueError("Rainbet api_host/brand_id are not configured.")
        self.settings = settings

    @property
    def _headers(self) -> dict[str, str]:
        origin = self.settings.site_origin
        return {
            "accept": "application/json,text/plain,*/*",
            "accept-language": "es-AR,es;q=0.9,en;q=0.8",
            "origin": origin,
            "referer": f"{origin}/",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
            ),
        }

    async def fetch_snapshot(self) -> dict[str, Any]:
        """Fetch the version manifest, then all chunks, merged into one snapshot."""

        merged = _empty_snapshot()
        async with httpx.AsyncClient(timeout=self.settings.timeout_seconds, follow_redirects=True) as client:
            manifest = await self._get(client, self.settings.feed_url(0))
            versions = _versions_from_manifest(manifest)

            # Some manifests already carry the data inline (no separate chunks).
            if not versions and any(isinstance(manifest.get(key), dict) for key in ("events", "tournaments")):
                _deep_merge(merged, manifest)
                return merged

            for version in versions:
                chunk = await self._get(client, self.settings.feed_url(version))
                _deep_merge(merged, chunk)
        return merged

    async def _get(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.settings.max_attempts):
            try:
                response = await client.get(url, headers=self._headers)
                response.raise_for_status()
                payload = response.json()
                return payload if isinstance(payload, dict) else {}
            except Exception as error:  # defensive polling
                last_error = error
                if attempt < self.settings.max_attempts - 1:
                    await asyncio.sleep(self.settings.retry_backoff_seconds)
        assert last_error is not None
        raise last_error


def _versions_from_manifest(manifest: dict[str, Any]) -> list[int]:
    versions: list[int] = []
    for key in ("top_events_versions", "rest_events_versions"):
        raw_versions = manifest.get(key)
        if not isinstance(raw_versions, list):
            continue
        for raw_version in raw_versions:
            try:
                version = int(raw_version)
            except (TypeError, ValueError):
                continue
            if version not in versions:
                versions.append(version)
    return versions


def _deep_merge(target: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for key, value in source.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[key] = value
    return target


def _empty_snapshot() -> dict[str, Any]:
    return {"sports": {}, "categories": {}, "tournaments": {}, "events": {}}
