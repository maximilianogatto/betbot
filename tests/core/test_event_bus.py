"""Tests del EventBus y del puerto EventListener."""
from __future__ import annotations

import time
import unittest

from core.event_bus import EventBus
from core.events import MatchLiveEvent, OddsChangedEvent
from core.listener import EventListener
from core.models import LiveWatchEntry, LiveWatchHit


class _Recorder(EventListener):
    def __init__(self) -> None:
        self.seen: list[object] = []

    async def handle(self, event: object) -> None:
        self.seen.append(event)


class _Exploding(EventListener):
    async def handle(self, event: object) -> None:
        raise RuntimeError("boom")


def _live_event(chat_id: int = 1, phase: str = "live") -> MatchLiveEvent:
    entry = LiveWatchEntry(
        id=1, chat_id=chat_id, home="A", away="B", league_hint=None, note=None,
        status="watching", matched_platform=None, matched_event_id=None,
        matched_minute=None, created_at="...", fired_at=None,
    )
    return MatchLiveEvent(hit=LiveWatchHit(entry=entry, phase=phase))


class EventBusTests(unittest.IsolatedAsyncioTestCase):
    async def test_publish_reaches_every_subscriber_of_that_type(self) -> None:
        bus = EventBus()
        first, second = _Recorder(), _Recorder()
        bus.subscribe(MatchLiveEvent, first.handle)
        bus.subscribe(MatchLiveEvent, second.handle)
        event = _live_event()

        result = await bus.publish(event)

        self.assertEqual(first.seen, [event])
        self.assertEqual(second.seen, [event])
        self.assertEqual((result.delivered, result.failed), (2, 0))

    async def test_listeners_of_other_event_types_are_not_called(self) -> None:
        bus = EventBus()
        listener = _Recorder()
        bus.subscribe(OddsChangedEvent, listener.handle)

        result = await bus.publish(_live_event())

        self.assertEqual(listener.seen, [])
        self.assertEqual((result.delivered, result.failed), (0, 0))

    async def test_a_failing_listener_does_not_block_the_others(self) -> None:
        """Un listener roto se aísla, pero la falla se reporta — no se traga."""

        bus = EventBus()
        healthy = _Recorder()
        bus.subscribe(MatchLiveEvent, _Exploding().handle)
        bus.subscribe(MatchLiveEvent, healthy.handle)
        event = _live_event()

        with self.assertLogs("core.event_bus", level="ERROR"):
            result = await bus.publish(event)

        self.assertEqual(healthy.seen, [event])
        self.assertEqual((result.delivered, result.failed), (1, 1))

    async def test_unsubscribe_stops_delivery(self) -> None:
        bus = EventBus()
        listener = _Recorder()
        bus.subscribe(MatchLiveEvent, listener.handle)
        bus.unsubscribe(MatchLiveEvent, listener.handle)

        result = await bus.publish(_live_event())

        self.assertEqual(listener.seen, [])
        self.assertEqual(result.delivered, 0)


class DomainEventTests(unittest.TestCase):
    def test_each_event_gets_its_own_timestamp(self) -> None:
        """Con `= datetime.now()` como default todos compartían la hora de import."""

        first = _live_event()
        time.sleep(0.01)
        second = _live_event()

        self.assertNotEqual(first.timestamp, second.timestamp)


if __name__ == "__main__":
    unittest.main()
