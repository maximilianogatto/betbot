from __future__ import annotations

import unittest

from core.models import CompetitionExtraction, CompetitionKey, EventKey, EventSnapshot, Odds1X2
from services.tracking import _normalize_extracted_match_for_persistence
from core.models import ActiveEventRecord


class TrackingDegradedRefreshTests(unittest.TestCase):
    def test_degraded_refresh_preserves_existing_asian_and_goal_line_markets(self) -> None:
        existing = ActiveEventRecord(
            id=1,
            tracked_competition_id=10,
            platform="bet365",
            competition_external_id="#topic#",
            external_event_id="193003460",
            home="Real Madrid",
            away="Real Oviedo",
            scheduled_label_date="2026-05-14",
            scheduled_label_time="20:30",
            scheduled_at="2026-05-14T23:30:00+00:00",
            event_url="https://example.test/event",
            odds_home=1.22,
            odds_draw=7.0,
            odds_away=11.0,
            markets_json=(
                '{"1x2":{"home":1.22,"draw":7.0,"away":11.0},'
                '"asian_handicap":{"market_id":"938","market_name":"Asian Handicap","selections":['
                '{"selection":"Real Madrid","line":"-1.5, -2.0","odds":1.975},'
                '{"selection":"Real Oviedo","line":"1.5, 2.0","odds":1.875}]},'
                '"goal_line":{"market_id":"10143","market_name":"Goal Line","selections":['
                '{"selection":"Over","line":"3.0, 3.5","odds":1.925},'
                '{"selection":"Under","line":"3.0, 3.5","odds":1.925}]}}'
            ),
            raw_payload_json='{"stats_url":"https://stats.test/match/1"}',
            alerted=False,
            is_active=True,
            first_seen_at="2026-05-12T00:00:00+00:00",
            last_seen_at="2026-05-12T00:00:00+00:00",
            created_at="2026-05-12T00:00:00+00:00",
            updated_at="2026-05-12T00:00:00+00:00",
        )

        extracted_match = EventSnapshot(
            key=EventKey(
                platform="bet365",
                competition_external_id="#topic#",
                external_event_id="193003460",
            ),
            competition_name="Spanish Primera",
            home="Real Madrid",
            away="Real Oviedo",
            scheduled_label_date="2026-05-14",
            scheduled_label_time="20:30",
            scheduled_at="2026-05-14T23:30:00+00:00",
            source_url="https://example.test/event",
            odds_1x2=Odds1X2(home=1.30, draw=6.5, away=9.5),
            extracted_at="2026-05-13T00:00:00+00:00",
            markets_payload={
                "1x2": {"home": 1.30, "draw": 6.5, "away": 9.5},
            },
            raw_payload={"capture_urls": {"league": "league-url"}},
        )

        extraction = CompetitionExtraction(
            competition=CompetitionKey(platform="bet365", competition_external_id="#topic#"),
            competition_name="Spanish Primera",
            source_url="https://example.test/league",
            events=[extracted_match],
            is_empty=False,
            is_provisional_name=False,
            extracted_at="2026-05-13T00:00:00+00:00",
            metadata={"degraded": True, "degraded_reason": "legacy_fallback"},
            raw_payload={"degraded": True},
        )

        normalized = _normalize_extracted_match_for_persistence(
            extracted_match,
            existing,
            extraction,
        )

        assert normalized.markets_payload is not None
        self.assertIn("asian_handicap", normalized.markets_payload)
        self.assertIn("goal_line", normalized.markets_payload)
        self.assertEqual(normalized.markets_payload["1x2"]["home"], 1.30)
        self.assertTrue(normalized.raw_payload["degraded"])
        self.assertEqual(normalized.raw_payload["degraded_reason"], "legacy_fallback")


if __name__ == "__main__":
    unittest.main()
