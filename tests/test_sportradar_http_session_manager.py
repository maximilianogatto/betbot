from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
import unittest

from sandbox.sportradar_http.session_manager import (
    BootstrapConfig,
    CapturedEndpoint,
    DEFAULT_ORIGIN,
    DEFAULT_REFERER,
    SignedToken,
    SportradarSessionState,
    build_replay_headers,
    is_blocked_payload,
    parse_signed_t,
    render_session_bootstrap_report,
)


class SportradarHttpSessionManagerTests(unittest.TestCase):
    def test_parse_signed_token_decodes_origin_data(self) -> None:
        token = (
            "exp=1779853984~acl=/*~"
            "data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayJ9~"
            "hmac=abc"
        )
        parsed = parse_signed_t(token)

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed["exp"], 1779853984)
        self.assertEqual(parsed["acl"], "/*")
        self.assertEqual(parsed["hmac"], "abc")
        self.assertEqual(parsed["data_json"]["o"], DEFAULT_ORIGIN)
        self.assertEqual(parsed["data_json"]["a"], "bet365")

    def test_blocked_payload_detects_exception_body(self) -> None:
        payload = {
            "doc": [
                {
                    "event": "Exception",
                    "data": {"name": "Unauthorized", "code": 403, "message": "Origin check failed"},
                }
            ]
        }

        self.assertTrue(is_blocked_payload(payload))
        self.assertTrue(is_blocked_payload(None, "Access Denied"))
        self.assertFalse(is_blocked_payload({"doc": [{"event": "match_markets", "data": {}}]}))

    def test_build_replay_headers_forces_origin_and_referer(self) -> None:
        headers = build_replay_headers(
            {
                "x": {
                    "accept-language": "es-AR,es;q=0.9",
                    "sec-fetch-site": "same-site",
                }
            }
        )

        self.assertEqual(headers["origin"], DEFAULT_ORIGIN)
        self.assertEqual(headers["referer"], DEFAULT_REFERER)
        self.assertEqual(headers["accept"], "application/json,text/plain,*/*")
        self.assertEqual(headers["accept-language"], "es-AR,es;q=0.9")
        self.assertEqual(headers["sec-fetch-site"], "same-site")

    def test_session_state_serializes_and_reports_usability(self) -> None:
        exp = int((datetime.now(UTC) + timedelta(hours=2)).timestamp())
        state = SportradarSessionState(
            generated_at="2026-05-26T00:00:00+00:00",
            headed=True,
            headless=False,
            bootstrap_urls=["https://statshub.sportradar.com/bet365/en/sport/1"],
            origin=DEFAULT_ORIGIN,
            referer=DEFAULT_REFERER,
            replay_headers=build_replay_headers(),
            cookies={"example": "cookie"},
            signed_token=SignedToken(raw=f"exp={exp}~acl=/*~hmac=abc", exp=exp, acl="/*"),
            sample_signed_url="https://sh.fn.sportradar.com/bet365/en/gismo/unified_sport_matches/1?T=x",
            endpoints_seen=["unified_sport_matches"],
            captured_endpoints=[
                CapturedEndpoint(
                    endpoint_key="unified_sport_matches",
                    url="https://sh.fn.sportradar.com/bet365/en/gismo/unified_sport_matches/1?T=x",
                    status=200,
                    body_size_bytes=123,
                    blocked=False,
                    expired=False,
                    elapsed_ms=12.5,
                )
            ],
            document_statuses={"https://statshub.sportradar.com/bet365/en/sport/1": 200},
            fetch_count=1,
            blocked_count=0,
            expired_count=0,
        )

        self.assertTrue(state.is_usable())
        encoded = json.dumps(state.to_json_dict())
        self.assertIn("unified_sport_matches", encoded)
        report = render_session_bootstrap_report([state])
        self.assertIn("Usable for HTTP replay", report)
        self.assertIn("unified_sport_matches", report)

    def test_bootstrap_config_defaults_to_headless(self) -> None:
        config = BootstrapConfig()

        self.assertFalse(config.headed)
        self.assertTrue(config.headless)
        self.assertGreaterEqual(len(config.bootstrap_urls), 1)


if __name__ == "__main__":
    unittest.main()

