from __future__ import annotations

import unittest

from bot.alerts import format_kickoff_labels, split_telegram_message


class BotAlertsTests(unittest.TestCase):
    def test_format_kickoff_labels_adds_weekday_prefix(self) -> None:
        self.assertEqual(
            format_kickoff_labels("2026-05-12", "19:00"),
            "Martes 2026-05-12 19:00",
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


if __name__ == "__main__":
    unittest.main()
