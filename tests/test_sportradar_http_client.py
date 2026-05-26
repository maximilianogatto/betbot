from __future__ import annotations

from datetime import UTC, datetime, timedelta
import unittest

import httpx

from sandbox.sportradar_http.http_client import (
    SportradarHTTPClient,
    SportradarHTTPError,
    summarize_payload,
)
from sandbox.sportradar_http.session_manager import (
    DEFAULT_ORIGIN,
    DEFAULT_REFERER,
    SignedToken,
    SportradarSessionState,
    build_replay_headers,
)


def make_state(*, token_raw: str = "exp=9999999999~acl=/*~hmac=abc") -> SportradarSessionState:
    exp = int((datetime.now(UTC) + timedelta(hours=3)).timestamp())
    return SportradarSessionState(
        generated_at="2026-05-26T00:00:00+00:00",
        headed=True,
        headless=False,
        bootstrap_urls=["https://statshub.sportradar.com/bet365/en/sport/1"],
        origin=DEFAULT_ORIGIN,
        referer=DEFAULT_REFERER,
        replay_headers=build_replay_headers(),
        cookies={},
        signed_token=SignedToken(raw=token_raw, exp=exp, acl="/*"),
        sample_signed_url="https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624678?T=x",
        endpoints_seen=["match_markets"],
        captured_endpoints=[],
        document_statuses={},
        fetch_count=1,
        blocked_count=0,
        expired_count=0,
    )


class FakeManager:
    def __init__(self) -> None:
        self.state = make_state(token_raw="exp=1111111111~acl=/*~hmac=old")
        self.refreshes = 0

    def refresh_session(self) -> SportradarSessionState:
        self.refreshes += 1
        self.state = make_state(token_raw=f"exp=9999999999~acl=/*~hmac=new{self.refreshes}")
        return self.state


class SportradarHTTPClientTests(unittest.TestCase):
    def test_get_gismo_uses_signed_token_and_headers(self) -> None:
        captured: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["origin"] = request.headers.get("origin", "")
            captured["referer"] = request.headers.get("referer", "")
            return httpx.Response(
                200,
                json={"queryUrl": "match_markets/61624678", "doc": [{"event": "match_markets", "data": {"markets": []}}]},
                request=request,
            )

        client = SportradarHTTPClient(
            session_state=make_state(),
            auto_refresh=False,
            transport=httpx.MockTransport(handler),
        )

        payload = client.get_gismo("match_markets/61624678")

        self.assertEqual(payload["queryUrl"], "match_markets/61624678")
        self.assertIn("/gismo/match_markets/61624678", captured["url"])
        self.assertIn("T=exp=9999999999", captured["url"])
        self.assertEqual(captured["origin"], DEFAULT_ORIGIN)
        self.assertEqual(captured["referer"], DEFAULT_REFERER)
        self.assertEqual(client.metrics.success_count, 1)

    def test_blocked_payload_raises_without_refresh(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"doc": [{"event": "Exception", "data": {"name": "Unauthorized", "code": 403}}]},
                request=request,
            )

        client = SportradarHTTPClient(
            session_state=make_state(),
            auto_refresh=False,
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(SportradarHTTPError) as caught:
            client.get_gismo("match_markets/61624678")

        self.assertTrue(caught.exception.validation.blocked)
        self.assertEqual(client.metrics.blocked_count, 1)

    def test_blocked_payload_refreshes_and_retries(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    200,
                    json={"doc": [{"event": "Exception", "data": {"name": "Unauthorized", "code": 403}}]},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"queryUrl": "match_markets/61624678", "doc": [{"event": "match_markets", "data": {}}]},
                request=request,
            )

        manager = FakeManager()
        client = SportradarHTTPClient(
            session_state=manager.state,
            session_manager=manager,
            auto_refresh=True,
            transport=httpx.MockTransport(handler),
        )

        payload = client.get_gismo("match_markets/61624678")

        self.assertEqual(payload["queryUrl"], "match_markets/61624678")
        self.assertEqual(manager.refreshes, 1)
        self.assertEqual(client.metrics.refresh_count, 1)
        self.assertEqual(client.metrics.success_count, 1)

    def test_blocked_payload_on_last_retry_still_gets_one_refresh_attempt(self) -> None:
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            if calls == 1:
                return httpx.Response(
                    500,
                    json={"error": "transient"},
                    request=request,
                )
            if calls == 2:
                return httpx.Response(
                    200,
                    json={"doc": [{"event": "Exception", "data": {"name": "Unauthorized", "code": 403}}]},
                    request=request,
                )
            return httpx.Response(
                200,
                json={"queryUrl": "match_markets/61624678", "doc": [{"event": "match_markets", "data": {}}]},
                request=request,
            )

        manager = FakeManager()
        client = SportradarHTTPClient(
            session_state=manager.state,
            session_manager=manager,
            auto_refresh=True,
            retries=1,
            transport=httpx.MockTransport(handler),
        )

        payload = client.get_gismo("match_markets/61624678")

        self.assertEqual(payload["queryUrl"], "match_markets/61624678")
        self.assertEqual(calls, 3)
        self.assertEqual(manager.refreshes, 1)
        self.assertEqual(client.metrics.refresh_count, 1)

    def test_empty_and_invalid_json_are_detected(self) -> None:
        responses = [
            httpx.Response(200, text="", request=httpx.Request("GET", "https://x/gismo/match_markets/1")),
            httpx.Response(200, text="<html>", request=httpx.Request("GET", "https://x/gismo/match_markets/1")),
        ]
        index = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal index
            response = responses[index]
            index += 1
            return response

        client = SportradarHTTPClient(
            session_state=make_state(),
            auto_refresh=False,
            retries=0,
            transport=httpx.MockTransport(handler),
        )

        with self.assertRaises(SportradarHTTPError) as empty_error:
            client.get_gismo("match_markets/1")
        self.assertTrue(empty_error.exception.validation.empty)

        with self.assertRaises(SportradarHTTPError) as invalid_error:
            client.get_gismo("match_markets/1")
        self.assertTrue(invalid_error.exception.validation.invalid_json)

    def test_summarize_payload_is_defensive(self) -> None:
        summary = summarize_payload({"queryUrl": "x", "doc": [{"event": "e", "data": {"b": 1, "a": 2}}]})

        self.assertEqual(summary["queryUrl"], "x")
        self.assertEqual(summary["doc_event"], "e")
        self.assertEqual(summary["data_keys"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
