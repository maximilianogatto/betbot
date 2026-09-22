"""Archivado de la serie de cuotas: sólo cambios, suspensiones y nunca romper el poll."""
from __future__ import annotations

from dataclasses import dataclass
import json
import unittest

from core.models import OddsSnapshot
from services.odds_archive import OddsArchiveService, payload_hash, should_archive


@dataclass
class Event:
    external_event_id: str = "ev-1"
    home: str = "Darwin"
    away: str = "Palmerston"
    scheduled_at: str | None = "2026-07-01T12:00:00+00:00"
    odds_home: float | None = 1.5
    odds_draw: float | None = 4.0
    odds_away: float | None = 6.0
    markets_payload: dict | None = None


class FakeArchive:
    def __init__(self) -> None:
        self.rows: list[OddsSnapshot] = []
        self.fail = False

    def archive_snapshots(self, snapshots):
        if self.fail:
            raise RuntimeError("base caída")
        self.rows.extend(snapshots)
        return len(snapshots)

    def last_snapshot(self, *, platform, external_event_id):
        found = [s for s in self.rows if s.external_event_id == external_event_id]
        return found[-1] if found else None

    def list_snapshots(self, **kwargs):
        return list(self.rows)

    def last_prematch_snapshot(self, **kwargs):
        return None


class HashTests(unittest.TestCase):
    def test_any_market_change_changes_the_hash(self) -> None:
        base = dict(odds_home=1.5, odds_draw=4.0, odds_away=6.0,
                    markets_json=json.dumps({"asian_handicap": {"line": "-1.5"}}))
        self.assertEqual(payload_hash(**base), payload_hash(**base))
        moved = dict(base, markets_json=json.dumps({"asian_handicap": {"line": "-2.5"}}))
        # El 1X2 no se movió, pero el handicap sí: tiene que archivarse igual.
        self.assertNotEqual(payload_hash(**base), payload_hash(**moved))

    def test_should_archive(self) -> None:
        self.assertTrue(should_archive(None, "abc"))
        previous = OddsSnapshot(platform="p", external_event_id="e", captured_at="t", payload_hash="abc")
        self.assertFalse(should_archive(previous, "abc"))
        self.assertTrue(should_archive(previous, "xyz"))


class ArchiveServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.archive = FakeArchive()
        self.clock_value = "2026-07-01T08:00:00+00:00"
        self.service = OddsArchiveService(self.archive, clock=lambda: _Clock(self.clock_value))

    def test_only_archives_when_the_price_changed(self) -> None:
        self.assertEqual(self.service.archive_events(platform="1xbet_http", events=[Event()]), 1)
        self.clock_value = "2026-07-01T08:02:00+00:00"
        self.assertEqual(self.service.archive_events(platform="1xbet_http", events=[Event()]), 0)
        self.clock_value = "2026-07-01T08:04:00+00:00"
        self.assertEqual(self.service.archive_events(
            platform="1xbet_http", events=[Event(odds_home=1.40)]), 1)
        self.assertEqual([s.odds_home for s in self.archive.rows], [1.5, 1.40])

    def test_a_suspended_market_is_archived_not_dropped(self) -> None:
        self.service.archive_events(platform="1xbet_http", events=[Event()])
        self.clock_value = "2026-07-01T08:05:00+00:00"
        self.service.archive_events(platform="1xbet_http", events=[
            Event(odds_home=None, odds_draw=None, odds_away=None)])
        self.assertTrue(self.archive.rows[-1].is_suspended)

    def test_markets_are_serialized_and_travel_with_the_snapshot(self) -> None:
        markets = {"asian_handicap": {"selections": [{"selection": "Darwin", "line": "-2.5", "odds": 1.66}]}}
        self.service.archive_events(platform="1xbet_http", events=[Event(markets_payload=markets)])
        self.assertEqual(json.loads(self.archive.rows[0].markets_json), markets)

    def test_a_failing_archive_never_breaks_the_poll(self) -> None:
        self.archive.fail = True
        self.assertEqual(self.service.archive_events(platform="1xbet_http", events=[Event()]), 0)

    def test_event_without_id_is_skipped(self) -> None:
        self.assertEqual(self.service.archive_events(
            platform="1xbet_http", events=[Event(external_event_id="")]), 0)


class _Clock:
    """Reloj mínimo: el servicio sólo le pide isoformat()."""

    def __init__(self, value: str) -> None:
        self.value = value

    def isoformat(self) -> str:
        return self.value


if __name__ == "__main__":
    unittest.main()
