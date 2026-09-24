"""1xBet client recovers on its own from a stuck connection pool (no bot restart)."""
from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from extractors.xbet_http import XBetHttpSettings
from extractors.xbet_http.client import XBetHttpClient

URL = "https://spinbetter.com/service-api/LineFeed/GetChampZip?champ=1&lng=en"


def _stuck(request: httpx.Request) -> httpx.Response:
    raise httpx.PoolTimeout("no connection available", request=request)


def _ok(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"Success": True, "Value": {"G": []}})


class StuckPoolTests(unittest.IsolatedAsyncioTestCase):
    def _client(self, *transports: httpx.MockTransport) -> tuple[XBetHttpClient, list[httpx.AsyncClient]]:
        real = httpx.AsyncClient
        pending = list(transports)
        built: list[httpx.AsyncClient] = []

        def build(**kwargs):
            kwargs.pop("proxy", None)
            built.append(real(transport=pending.pop(0), **kwargs))
            return built[-1]

        patcher = patch("extractors.xbet_http.client.httpx.AsyncClient", side_effect=build)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings = XBetHttpSettings(max_attempts=2, retry_backoff_seconds=0, min_request_interval_seconds=0)
        return XBetHttpClient(settings), built

    async def test_a_pool_timeout_rebuilds_the_client_and_the_retry_succeeds(self) -> None:
        client, built = self._client(httpx.MockTransport(_stuck), httpx.MockTransport(_ok))

        payload = await client.fetch_champ_zip(URL)

        self.assertTrue(payload["Success"])
        self.assertEqual(len(built), 2)
        self.assertTrue(built[0].is_closed)
        self.assertIs(client._http, built[1])
        await client.aclose()

    async def test_a_replacement_built_meanwhile_is_not_discarded(self) -> None:
        client, built = self._client(httpx.MockTransport(_stuck), httpx.MockTransport(_ok))
        stuck = client._get_client()
        fresh = await self._rebuild(client, stuck)

        await client._discard_stuck_pool(stuck)  # a second request that timed out late

        self.assertIs(client._http, fresh)
        self.assertFalse(fresh.is_closed)
        await client.aclose()

    async def _rebuild(self, client: XBetHttpClient, stuck: httpx.AsyncClient) -> httpx.AsyncClient:
        await client._discard_stuck_pool(stuck)
        return client._get_client()

    async def test_other_errors_keep_the_pool(self) -> None:
        def unavailable(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503)

        client, built = self._client(httpx.MockTransport(unavailable))

        with self.assertRaises(Exception):
            await client.fetch_champ_zip(URL)

        self.assertEqual(len(built), 1)
        self.assertFalse(built[0].is_closed)
        await client.aclose()


if __name__ == "__main__":
    unittest.main()
