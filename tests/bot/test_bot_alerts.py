from __future__ import annotations

import json
import unittest

from dataclasses import replace

from bot.alerts import (
    build_match_reminder_alert_message,
    format_display_datetime,
    format_kickoff_labels,
    format_kickoff_text,
    split_telegram_message,
)
from storage.tracking_repository import ActiveEventRecord, TrackedCompetition


def _tracked_league() -> TrackedCompetition:
    return TrackedCompetition(
        id=1,
        platform="bet365",
        source_url="https://example.test/league",
        competition_external_id="#topic#",
        competition_name="Spanish Primera",
        metadata_json=None,
        needs_name_resolution=False,
        enabled=True,
        last_synced_at=None,
        consecutive_unavailable_refreshes=0,
        last_unavailable_refresh_at=None,
        last_unavailable_reason=None,
        last_unavailable_notification_at=None,
        created_at="2026-05-13T00:00:00+00:00",
        updated_at="2026-05-13T00:00:00+00:00",
    )


def _match_with_markets(markets_payload: dict[str, object] | None) -> ActiveEventRecord:
    return ActiveEventRecord(
        id=1,
        tracked_competition_id=1,
        platform="bet365",
        competition_external_id="#topic#",
        external_event_id="193003384",
        home="Elche",
        away="CD Alaves",
        scheduled_label_date="2026-05-13",
        scheduled_label_time="19:00",
        scheduled_at="2026-05-13T22:00:00+00:00",
        event_url="https://example.test/event",
        odds_home=2.15,
        odds_draw=3.10,
        odds_away=3.40,
        markets_json=(
            json.dumps(markets_payload, ensure_ascii=False)
            if markets_payload is not None
            else None
        ),
        raw_payload_json=None,
        alerted=False,
        is_active=True,
        first_seen_at="2026-05-13T00:00:00+00:00",
        last_seen_at="2026-05-13T00:00:00+00:00",
        created_at="2026-05-13T00:00:00+00:00",
        updated_at="2026-05-13T00:00:00+00:00",
    )


class BotAlertsTests(unittest.TestCase):
    def test_format_kickoff_text_converts_utc_to_display_timezone(self) -> None:
        # Real bug: kickoff at 23:15 UTC was shown as 23:15 instead of the local
        # 20:15 (Argentina, UTC-3). Must convert from the offset-aware timestamp.
        match = replace(
            _match_with_markets(None),
            scheduled_at="2026-05-30T23:15:00+00:00",
            scheduled_label_date="2026-05-30",
            scheduled_label_time="23:15",
        )

        text = format_kickoff_text(match)

        self.assertIn("20:15", text)
        self.assertNotIn("23:15", text)

    def test_format_kickoff_labels_uses_short_visible_format(self) -> None:
        self.assertEqual(
            format_kickoff_labels("2026-05-12", "19:00"),
            "Mar 12/05 19:00",
        )

    def test_format_display_datetime_formats_iso_without_year(self) -> None:
        self.assertEqual(
            format_display_datetime("2026-05-13T22:00:00+00:00"),
            "Mié 13/05 19:00",
        )

    def test_split_telegram_message_preserves_complete_lines_when_possible(self) -> None:
        text = "\n".join(
            [
                "Linea 1",
                "Linea 2",
                "Linea 3",
                "Linea 4",
            ]
        )

        chunks = split_telegram_message(text, max_len=15)

        self.assertGreater(len(chunks), 1)
        self.assertEqual("".join(chunk if index == 0 else "\n" + chunk for index, chunk in enumerate(chunks)), text)
        self.assertTrue(all(len(chunk) <= 15 for chunk in chunks))

    def test_match_reminder_shows_ah_and_gl_when_both_exist(self) -> None:
        message = build_match_reminder_alert_message(
            _tracked_league(),
            _match_with_markets(
                {
                    "asian_handicap": {
                        "selections": [
                            {"selection": "Elche", "line": "-0.5", "odds": 1.9},
                            {"selection": "CD Alaves", "line": "0.5", "odds": 1.95},
                        ]
                    },
                    "goal_line": {
                        "selections": [
                            {"selection": "Over", "line": "2.5", "odds": 1.85},
                            {"selection": "Under", "line": "2.5", "odds": 2.0},
                        ]
                    },
                }
            ),
        )

        self.assertIn("📐 AH", message)
        self.assertIn("📏 GL", message)
        self.assertNotIn("Sin línea valor", message)
        self.assertIn("Mié 13/05 19:00", message)
        self.assertNotIn("2026", message)

    def test_match_reminder_hides_ah_when_missing(self) -> None:
        message = build_match_reminder_alert_message(
            _tracked_league(),
            _match_with_markets(
                {
                    "goal_line": {
                        "selections": [
                            {"selection": "Over", "line": "2.5", "odds": 1.85},
                            {"selection": "Under", "line": "2.5", "odds": 2.0},
                        ]
                    },
                }
            ),
        )

        self.assertNotIn("📐 AH", message)
        self.assertIn("📏 GL", message)
        self.assertNotIn("Sin línea valor", message)
        self.assertNotIn("2026", message)

    def test_match_reminder_hides_gl_when_missing(self) -> None:
        message = build_match_reminder_alert_message(
            _tracked_league(),
            _match_with_markets(
                {
                    "asian_handicap": {
                        "selections": [
                            {"selection": "Elche", "line": "-0.5", "odds": 1.9},
                            {"selection": "CD Alaves", "line": "0.5", "odds": 1.95},
                        ]
                    },
                }
            ),
        )

        self.assertIn("📐 AH", message)
        self.assertNotIn("📏 GL", message)
        self.assertNotIn("Sin línea valor", message)
        self.assertNotIn("2026", message)

    def test_match_reminder_hides_both_lines_when_both_missing(self) -> None:
        match = _match_with_markets(None)
        message = build_match_reminder_alert_message(
            _tracked_league(),
            match,
        )

        self.assertNotIn("📐 AH", message)
        self.assertNotIn("📏 GL", message)
        self.assertNotIn("Sin línea valor", message)
        self.assertNotIn("2026", message)
        self.assertIn("2026-05-13T22:00:00+00:00", match.scheduled_at)


if __name__ == "__main__":
    unittest.main()
