from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from bot import handlers


class TrackUrlCustomNameTests(unittest.IsolatedAsyncioTestCase):
    async def _run(self, args: list[str]) -> dict:
        service = SimpleNamespace(
            create_pending_track_from_url=AsyncMock(return_value=SimpleNamespace(ok=True, message="ok"))
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(message=message, effective_chat=SimpleNamespace(id=1))
        context = SimpleNamespace(args=args)
        with patch("bot.handlers.get_tracking_service", return_value=service), patch(
            "bot.handlers.reply_with_result", AsyncMock()
        ):
            await handlers.track_url_command(update, context)
        return service.create_pending_track_from_url.await_args.kwargs

    async def test_url_with_custom_name(self) -> None:
        kw = await self._run(
            ["https://x/getprematchgameall/as/28/?games=,1,2", "|", "Australia", "NPL", "Northern", "NSW"]
        )
        self.assertEqual(kw["url"], "https://x/getprematchgameall/as/28/?games=,1,2")
        self.assertEqual(kw["custom_name"], "Australia NPL Northern NSW")

    async def test_url_without_name(self) -> None:
        kw = await self._run(["https://x/getprematchgameall/as/28/?games=,1,2"])
        self.assertEqual(kw["url"], "https://x/getprematchgameall/as/28/?games=,1,2")
        self.assertIsNone(kw["custom_name"])


if __name__ == "__main__":
    unittest.main()
