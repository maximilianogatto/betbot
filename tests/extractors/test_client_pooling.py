from __future__ import annotations

import unittest


def _live_extractors():
    from extractors.betovo_http.extractor import BetovoHttpExtractor
    from extractors.betwarrior_http.extractor import BetWarriorHttpExtractor
    from extractors.bz_http.extractor import BzHttpExtractor
    from extractors.mrpunter_http.extractor import MrPunterHttpExtractor
    from extractors.mystake_http.extractor import MystakeHttpExtractor
    from extractors.solcasino_http.extractor import SolcasinoHttpExtractor
    from extractors.xbet_http.extractor import XBetHttpExtractor

    return [
        BzHttpExtractor,
        BetovoHttpExtractor,
        BetWarriorHttpExtractor,
        MystakeHttpExtractor,
        SolcasinoHttpExtractor,
        MrPunterHttpExtractor,
        XBetHttpExtractor,
    ]


class PersistentClientPoolTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_extractors_reuse_one_client_and_close_on_stop(self) -> None:
        for factory in _live_extractors():
            ext = factory()
            client = ext._client
            # Same keep-alive client instance reused across calls.
            first = client._get_client()
            self.assertIs(client._get_client(), first, f"{factory.__name__} did not reuse client")
            self.assertFalse(first.is_closed)

            # stop() closes the underlying httpx client.
            await ext.stop()
            self.assertTrue(first.is_closed, f"{factory.__name__} did not close on stop")
            self.assertIsNone(client._http)

            # After close, a fresh client is built on demand (no reuse of a closed one).
            rebuilt = client._get_client()
            self.assertIsNot(rebuilt, first)
            await rebuilt.aclose()


if __name__ == "__main__":
    unittest.main()
