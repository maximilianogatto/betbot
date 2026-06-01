from __future__ import annotations

import unittest

from sandbox.sofascore_http.capture_traffic import (
    build_endpoint_index,
    endpoint_key,
    is_sofascore_api_url,
    normalize_endpoint_path,
)
from sandbox.sofascore_http.client import SofaScoreHTTPClient
from sandbox.sofascore_http.client import SofaScoreHTTPSettings
from sandbox.sofascore_http.normalizers import (
    build_match_snapshot,
    normalize_1x2_odds,
    normalize_fixture,
    normalize_incident,
)


class FakeResponse:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = "fake-response"

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.calls = 0

    def get(self, url: str, **kwargs):
        self.calls += 1
        return self.response


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.value += seconds


class SofaScoreCaptureTests(unittest.TestCase):
    def test_filter_keeps_only_sofascore_api_urls(self) -> None:
        self.assertTrue(is_sofascore_api_url("https://www.sofascore.com/api/v1/event/123"))
        self.assertTrue(is_sofascore_api_url("https://api.sofascore.com/api/v1/event/123"))
        self.assertFalse(is_sofascore_api_url("https://www.sofascore.com/_next/static/app.js"))
        self.assertFalse(is_sofascore_api_url("https://ads.example.test/api/v1/event/123"))

    def test_normalize_endpoint_path_collapses_ids_and_dates(self) -> None:
        url = "https://www.sofascore.com/api/v1/unique-tournament/8/scheduled-events/2026-06-01"
        self.assertEqual(
            normalize_endpoint_path(url),
            "/api/v1/unique-tournament/{id}/scheduled-events/{date}",
        )
        self.assertEqual(
            endpoint_key(url),
            "unique-tournament/{id}/scheduled-events/{date}",
        )

    def test_endpoint_index_groups_variable_ids(self) -> None:
        records = [
            {
                "endpoint_key": "event/{id}",
                "normalized_path": "/api/v1/event/{id}",
                "status": 200,
                "method": "GET",
                "url": "https://www.sofascore.com/api/v1/event/1",
                "body_size_bytes": 10,
                "body_json": {"event": {}},
            },
            {
                "endpoint_key": "event/{id}",
                "normalized_path": "/api/v1/event/{id}",
                "status": 200,
                "method": "GET",
                "url": "https://www.sofascore.com/api/v1/event/2",
                "body_size_bytes": 20,
                "body_json": {"event": {}},
            },
        ]

        index = build_endpoint_index(records)

        self.assertEqual(index["event/{id}"]["count"], 2)
        self.assertEqual(index["event/{id}"]["body_size_min"], 10)
        self.assertEqual(index["event/{id}"]["body_size_max"], 20)


class SofaScoreNormalizerTests(unittest.TestCase):
    def test_normalize_fixture_maps_live_event(self) -> None:
        fixture = normalize_fixture(
            {
                "id": 99,
                "customId": "abc",
                "slug": "away-home",
                "startTimestamp": 1780322400,
                "status": {"type": "inprogress", "description": "2nd half"},
                "homeTeam": {"id": 1, "name": "Home"},
                "awayTeam": {"id": 2, "name": "Away"},
                "homeScore": {"current": 2},
                "awayScore": {"current": 1},
                "season": {"id": 3},
                "tournament": {
                    "name": "Stage",
                    "uniqueTournament": {"id": 4, "name": "League"},
                },
            }
        )

        self.assertEqual(fixture["match_id"], "99")
        self.assertEqual(fixture["home"], "Home")
        self.assertEqual(fixture["league_id"], "4")
        self.assertEqual(fixture["score_home"], 2)

    def test_normalize_1x2_odds_converts_fractional_to_decimal(self) -> None:
        odds = normalize_1x2_odds(
            {
                "markets": [
                    {
                        "marketGroup": "1X2",
                        "choices": [
                            {"name": "1", "fractionalValue": "4/7"},
                            {"name": "X", "fractionalValue": "23/10"},
                            {"name": "2", "fractionalValue": "9/2"},
                        ],
                    }
                ]
            }
        )

        self.assertEqual(odds, {"home": 1.571429, "draw": 3.3, "away": 5.5})

    def test_incident_normalizer_drops_large_player_payloads(self) -> None:
        incident = normalize_incident(
            {
                "id": 10,
                "incidentType": "goal",
                "player": {"id": 20, "name": "Scorer", "marketValue": 999, "country": {"name": "X"}},
            }
        )

        self.assertEqual(incident["player"], {"id": "20", "name": "Scorer"})
        self.assertNotIn("marketValue", incident["player"])

    def test_match_snapshot_is_compact_and_serializable(self) -> None:
        snapshot = build_match_snapshot(
            event={"id": 1, "homeTeam": {"name": "A"}, "awayTeam": {"name": "B"}},
            statistics=[],
            incidents=[{"incidentType": "goal", "player": {"id": 2, "name": "P", "extra": "drop"}}],
            lineups={},
            h2h={},
            win_probability={},
            odds={},
        )

        self.assertEqual(snapshot["live_state"]["incidents"][0]["player"], {"id": "2", "name": "P"})
        self.assertFalse(snapshot["coverage"]["has_statistics"])


class SofaScoreHTTPClientTests(unittest.TestCase):
    def test_category_tournaments_flattens_groups(self) -> None:
        response = FakeResponse(
            200,
            {
                "groups": [
                    {"uniqueTournaments": [{"id": 1, "name": "League A"}]},
                    {"uniqueTournaments": [{"id": 2, "name": "League B"}]},
                ]
            },
        )
        tournaments = SofaScoreHTTPClient(session=FakeSession(response)).get_category_tournaments(34)

        self.assertEqual([item["id"] for item in tournaments], [1, 2])

    def test_optional_404_returns_empty_payload(self) -> None:
        incidents = SofaScoreHTTPClient(
            session=FakeSession(FakeResponse(404, {"error": {"message": "Not Found"}}))
        ).get_event_incidents(123)

        self.assertEqual(incidents, [])

    def test_client_reuses_in_memory_cache(self) -> None:
        session = FakeSession(FakeResponse(200, {"categories": []}))
        client = SofaScoreHTTPClient(
            SofaScoreHTTPSettings(cache_ttl_seconds=60),
            session=session,
        )

        client.get_categories()
        client.get_categories()

        self.assertEqual(session.calls, 1)
        self.assertEqual(client.cache_hit_count, 1)

    def test_client_rate_limits_uncached_requests(self) -> None:
        session = FakeSession(FakeResponse(200, {"categories": []}))
        clock = FakeClock()
        client = SofaScoreHTTPClient(
            SofaScoreHTTPSettings(
                cache_ttl_seconds=0,
                min_request_interval_seconds=0.5,
            ),
            session=session,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )

        client.get_categories()
        client.get_categories()

        self.assertEqual(session.calls, 2)
        self.assertEqual(clock.sleeps, [0.5])


if __name__ == "__main__":
    unittest.main()
