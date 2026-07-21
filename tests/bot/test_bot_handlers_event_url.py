from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from interfaces.telegram.handlers import (
    MATCHES_ACTIVE_CONTEXT_KEY,
    MATCHES_SELECTED_TRACK_CONTEXT_KEY,
    event_url_command,
)
from core.models import ActiveEventRecord


def _active_event(
    *,
    record_id: int,
    tracked_competition_id: int,
    platform: str,
    event_url: str | None,
    home: str = "Sevilla",
    away: str = "Real Madrid",
) -> ActiveEventRecord:
    return ActiveEventRecord(
        id=record_id,
        tracked_competition_id=tracked_competition_id,
        platform=platform,
        competition_external_id="league-1",
        external_event_id=f"event-{record_id}",
        home=home,
        away=away,
        scheduled_label_date="Dom 24/05",
        scheduled_label_time="17:00",
        scheduled_at="2026-05-24T17:00:00+00:00",
        event_url=event_url,
        odds_home=3.2,
        odds_draw=3.5,
        odds_away=2.1,
        markets_json=None,
        raw_payload_json=None,
        alerted=False,
        is_active=True,
        first_seen_at="2026-05-20T00:00:00+00:00",
        last_seen_at="2026-05-20T00:00:00+00:00",
        created_at="2026-05-20T00:00:00+00:00",
        updated_at="2026-05-20T00:00:00+00:00",
    )


def _grouped_matches() -> list[list[ActiveEventRecord]]:
    """Two physical matches; the first is cross-book (two houses)."""

    return [
        [
            _active_event(
                record_id=1,
                tracked_competition_id=10,
                platform="bet365",
                event_url="https://bet365.test/event-1",
                home="Sevilla",
                away="Real Madrid",
            ),
            _active_event(
                record_id=2,
                tracked_competition_id=11,
                platform="betovo",
                event_url="https://betovo.test/event-1",
                home="Sevilla",
                away="Real Madrid",
            ),
        ],
        [
            _active_event(
                record_id=3,
                tracked_competition_id=10,
                platform="bet365",
                event_url="https://bet365.test/event-2",
                home="Valencia",
                away="Getafe",
            ),
        ],
    ]


class EventUrlCommandTests(unittest.IsolatedAsyncioTestCase):
    def _make_update_context(self, args: list[str], user_data: dict):
        message = SimpleNamespace(text=" ".join(args), reply_text=AsyncMock())
        context = SimpleNamespace(args=args, user_data=user_data)
        update = SimpleNamespace(message=message)
        return update, context, message

    async def test_event_url_lists_every_house_in_group(self) -> None:
        grouped = _grouped_matches()
        update, context, message = self._make_update_context(
            ["2"],  # "1 - Ver todos", so 2 -> grouped[0]
            {
                MATCHES_ACTIVE_CONTEXT_KEY: grouped,
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: {"id": 7, "name": "La Liga"},
            },
        )

        with patch(
            "adapters.storage.SqliteStorage.get_tracked_competition",
            return_value=None,
        ):
            await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("Sevilla vs Real Madrid", sent)
        self.assertIn("https://bet365.test/event-1", sent)
        self.assertIn("https://betovo.test/event-1", sent)
        # Should not leak the other physical match.
        self.assertNotIn("event-2", sent)

    async def test_event_url_maps_number_to_correct_group(self) -> None:
        grouped = _grouped_matches()
        update, context, message = self._make_update_context(
            ["3"],  # 3 -> grouped[1]
            {
                MATCHES_ACTIVE_CONTEXT_KEY: grouped,
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: {"id": 7, "name": "La Liga"},
            },
        )

        with patch(
            "adapters.storage.SqliteStorage.get_tracked_competition",
            return_value=None,
        ):
            await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("Valencia vs Getafe", sent)
        self.assertIn("https://bet365.test/event-2", sent)

    async def test_event_url_number_one_is_ver_todos(self) -> None:
        grouped = _grouped_matches()
        update, context, message = self._make_update_context(
            ["1"],
            {
                MATCHES_ACTIVE_CONTEXT_KEY: grouped,
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: {"id": 7, "name": "La Liga"},
            },
        )

        await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("Ver todos", sent)

    async def test_event_url_without_selected_league_dict(self) -> None:
        update, context, message = self._make_update_context(
            ["2"],
            {
                MATCHES_ACTIVE_CONTEXT_KEY: _grouped_matches(),
                # Stale/missing unified-league selection.
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: None,
            },
        )

        await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("No tengo una liga seleccionada", sent)

    async def test_event_url_without_active_matches(self) -> None:
        update, context, message = self._make_update_context(
            ["2"],
            {MATCHES_SELECTED_TRACK_CONTEXT_KEY: {"id": 7, "name": "La Liga"}},
        )

        await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("No tengo una lista reciente", sent)

    async def test_event_url_house_without_link_shows_warning(self) -> None:
        grouped = [
            [
                _active_event(
                    record_id=1,
                    tracked_competition_id=10,
                    platform="bet365",
                    event_url=None,
                ),
            ],
        ]
        update, context, message = self._make_update_context(
            ["2"],
            {
                MATCHES_ACTIVE_CONTEXT_KEY: grouped,
                MATCHES_SELECTED_TRACK_CONTEXT_KEY: {"id": 7, "name": "La Liga"},
            },
        )

        with patch(
            "adapters.storage.SqliteStorage.get_tracked_competition",
            return_value=None,
        ):
            await event_url_command(update, context)

        sent = message.reply_text.await_args_list[0].args[0]
        self.assertIn("Sin link directo disponible", sent)


if __name__ == "__main__":
    unittest.main()
