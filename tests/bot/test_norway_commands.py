from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from bot.handlers import (
    no_help_command,
    no_leagues_command,
    no_standings_command,
    no_fixtures_command,
    no_today_command,
    no_match_command,
)

def _update():
    message = SimpleNamespace(reply_text=AsyncMock())
    return SimpleNamespace(message=message), message

class NoCommandTests(unittest.IsolatedAsyncioTestCase):
    def _patch_client(self, tables_return):
        client = MagicMock()
        client.get_tables.return_value = tables_return
        client.close = MagicMock()
        return patch("stats_providers.norway_http.client.NorwayNFFHTTPClient", return_value=client)

    async def test_help_command(self) -> None:
        update, message = _update()
        await no_help_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Guía de Estadísticas de la Federación de Noruega", out)
        self.assertIn("`/no_leagues`", out)

    async def test_leagues_lists_codes(self) -> None:
        update, message = _update()
        await no_leagues_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Toppserien", out)
        self.assertIn("`NO1`", out)

    async def test_standings_renders_table(self) -> None:
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Plass"}, {"text": "Lag"}, {"text": "Kamper"}, {"text": "Vunnet"}, {"text": "Uavgjort"}, {"text": "Tap"}, {"text": "Mål"}, {"text": "Diff"}, {"text": "Poeng"}],
                    [{"text": "1"}, {"text": "SK Brann"}, {"text": "10"}, {"text": "9"}, {"text": "1"}, {"text": "0"}, {"text": "34 - 3"}, {"text": "31"}, {"text": "28"}],
                    [{"text": "2"}, {"text": "Rosenborg BK"}, {"text": "10"}, {"text": "6"}, {"text": "2"}, {"text": "2"}, {"text": "14 - 7"}, {"text": "7"}, {"text": "20"}]
                ]
            }
        ]
        with self._patch_client(tables):
            await no_standings_command(update, SimpleNamespace(args=["NO1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Posiciones: Toppserien (2026)", out)
        self.assertIn("SK Brann", out)
        self.assertIn("Rosenborg BK", out)

    async def test_fixtures_lists_matches_with_ids(self) -> None:
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Runde"}, {"text": "Dato"}, {"text": "Dag"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Kampnr."}],
                    [
                        {"text": "1"}, 
                        {"text": "20.03.2026"}, 
                        {"text": "fredag"}, 
                        {"text": "18:00"}, 
                        {"text": "Bodø/Glimt"}, 
                        {"text": "0 - 0"}, 
                        {"text": "Hønefoss BK"}, 
                        {"text": "Aspmyra"}, 
                        {"text": "99220001001", "hrefs": ["/fotballdata/kamp/?fiksId=8998012"]}
                    ]
                ]
            }
        ]
        with self._patch_client(tables):
            await no_fixtures_command(update, SimpleNamespace(args=["NO1"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Bodø/Glimt", out)
        self.assertIn("8998012", out)

    async def test_today_filters_today_matches(self) -> None:
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Turnering"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Referat"}, {"text": "Spillform"}],
                    [
                        {"text": "Toppserien"}, 
                        {"text": "18:00"}, 
                        {"text": "Bodø/Glimt Today"}, 
                        {"text": "vs"}, 
                        {"text": "Hønefoss BK Today"}, 
                        {"text": "Aspmyra"}, 
                        {"text": "Kampfakta", "hrefs": ["/fotballdata/kamp/?fiksId=8998012"]}, 
                        {"text": "11 MOT 11"}
                    ]
                ]
            }
        ]
        with self._patch_client(tables):
            await no_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("Bodø/Glimt Today", out)
        self.assertIn("8998012", out)

    async def test_match_command_details(self) -> None:
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Runde"}, {"text": "Dato"}, {"text": "Dag"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Kampnr."}],
                    [
                        {"text": "1"}, 
                        {"text": "20.03.2026"}, 
                        {"text": "fredag"}, 
                        {"text": "18:00"}, 
                        {"text": "Bodø/Glimt"}, 
                        {"text": "0 - 0"}, 
                        {"text": "Hønefoss BK"}, 
                        {"text": "Aspmyra"}, 
                        {"text": "99220001001", "hrefs": ["/fotballdata/kamp/?fiksId=8998012"]}
                    ]
                ]
            }
        ]
        with self._patch_client(tables):
            await no_match_command(update, SimpleNamespace(args=["8998012"]))
        self.assertGreaterEqual(message.reply_text.await_count, 2)
        out = message.reply_text.await_args.args[0]
        self.assertIn("Bodø/Glimt 0-0 Hønefoss BK", out)
        self.assertIn("FORMA", out)

    async def test_today_uses_match_id_not_tournament_id(self) -> None:
        # The Turnering cell carries the TOURNAMENT fiksId; only /fotballdata/kamp/
        # is the match id. /no_today must show the match id (else /no_match 404s).
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Turnering"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Referat"}],
                    [
                        {"text": "Norsk Tipping-ligaen avd. 5", "hrefs": ["/fotballdata/turnering/hjem/?fiksId=205690"]},
                        {"text": "19:00"},
                        {"text": "Ulfstind", "hrefs": ["/fotballdata/lag/hjem/?fiksId=206664"]},
                        {"text": "3 - 0", "hrefs": ["/fotballdata/kamp/?fiksId=8995864"]},
                        {"text": "Fløya", "hrefs": ["/fotballdata/lag/hjem/?fiksId=651"]},
                        {"text": "Tønsnes", "hrefs": ["/fotballdata/anlegg/hjem/?fiksId=14918"]},
                        {"text": "Kampfakta", "hrefs": ["/fotballdata/kamp/?fiksId=8995864"]},
                    ],
                ]
            }
        ]
        with self._patch_client(tables):
            await no_today_command(update, SimpleNamespace())
        out = message.reply_text.await_args.args[0]
        self.assertIn("8995864", out)       # match id
        self.assertNotIn("205690", out)     # NOT the tournament id

    async def test_match_shows_real_league_not_hardcoded_toppserien(self) -> None:
        update, message = _update()
        tables = [
            {
                "rows": [
                    [{"text": "Turnering"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Referat"}],
                    [
                        {"text": "Norsk Tipping-ligaen avd. 5", "hrefs": ["/fotballdata/turnering/hjem/?fiksId=205690"]},
                        {"text": "19:00"},
                        {"text": "Ulfstind"},
                        {"text": "3 - 0", "hrefs": ["/fotballdata/kamp/?fiksId=8995864"]},
                        {"text": "Fløya"},
                        {"text": "Tønsnes"},
                        {"text": "Kampfakta", "hrefs": ["/fotballdata/kamp/?fiksId=8995864"]},
                    ],
                ]
            }
        ]
        with self._patch_client(tables):
            await no_match_command(update, SimpleNamespace(args=["8995864"]))
        out = message.reply_text.await_args.args[0]
        self.assertIn("Norsk Tipping-ligaen avd. 5", out)  # liga real, no hardcoded
        self.assertNotIn("Toppserien", out)
        self.assertIn("FORMA", out)  # match_report (lineup detector) corrió

    async def test_match_pulls_standings_from_match_tournament(self) -> None:
        # The kamp page links its tournament by fiksId; match_report must fetch
        # THAT tournament's standings/fixtures so the table shows positions for
        # ANY division, not just Toppserien.
        from bot.special_leagues import NorwayLeagues

        kamp_html = (
            "<html><title>Varhaug - Viking 2 - 11.06.2026 19:00</title>"
            '<a href="/fotballdata/turnering/hjem/?fiksId=205689">Norsk Tipping-ligaen avd. 4</a>'
            "</html>"
        )
        tour_tables = [
            {  # standings
                "rows": [
                    [{"text": "Plass"}, {"text": "Lag"}, {"text": "Kamper"}, {"text": "V"}, {"text": "U"}, {"text": "T"}, {"text": "Diff"}, {"text": "Poeng"}],
                    [{"text": "3"}, {"text": "Varhaug"}, {"text": "9"}, {"text": "4"}, {"text": "3"}, {"text": "2"}, {"text": "5"}, {"text": "15"}],
                    [{"text": "4"}, {"text": "Viking 2"}, {"text": "9"}, {"text": "4"}, {"text": "2"}, {"text": "3"}, {"text": "2"}, {"text": "14"}],
                ]
            },
            {  # fixtures
                "rows": [
                    [{"text": "Runde"}, {"text": "Dato"}, {"text": "Dag"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Kampnr."}],
                    [{"text": "8"}, {"text": "01.06.2026"}, {"text": "søn"}, {"text": "14:00"}, {"text": "Varhaug"}, {"text": "2 - 1"}, {"text": "Bryne 2"}, {"text": "X"}, {"text": "1", "hrefs": ["/fotballdata/kamp/?fiksId=1"]}],
                ]
            },
        ]
        client = MagicMock()
        client.get_html.return_value = kamp_html
        client.get_tables.return_value = tour_tables
        client.close = MagicMock()
        no = NorwayLeagues(client)
        report = no.match_report("8992950")
        self.assertIn("Norsk Tipping-ligaen avd. 4", report)
        self.assertIn("3rd", report)   # Varhaug standings position
        self.assertIn("4th", report)   # Viking 2 standings position

    async def test_match_score_not_invented_from_title(self) -> None:
        # Title "Alta - Tromsø 2 - 12.06.2026 ..." must NOT yield a "2-12" score;
        # an unplayed match (Resultat "-") stays Scheduled with no score.
        from bot.special_leagues import NorwayLeagues

        kamp_html = (
            "<html><title>Alta - Troms&#xF8; 2 - 12.06.2026 18:30 - Norges Fotballforbund</title>"
            '<a href="/fotballdata/turnering/hjem/?fiksId=205690">Norsk Tipping-ligaen avd. 5</a>'
            "</html>"
        )
        tour_tables = [
            {
                "rows": [
                    [{"text": "Runde"}, {"text": "Dato"}, {"text": "Dag"}, {"text": "Tid"}, {"text": "Hjemmelag"}, {"text": "Resultat"}, {"text": "Bortelag"}, {"text": "Bane"}, {"text": "Kampnr."}],
                    [{"text": "10"}, {"text": "12.06.2026"}, {"text": "fre"}, {"text": "18:30"}, {"text": "Alta"}, {"text": "-"}, {"text": "Tromsø 2"}, {"text": "X"}, {"text": "8995862", "hrefs": ["/fotballdata/kamp/?fiksId=8995862"]}],
                ]
            }
        ]
        client = MagicMock()
        client.get_html.return_value = kamp_html
        client.get_tables.return_value = tour_tables
        client.close = MagicMock()
        report = NorwayLeagues(client).match_report("8995862")
        self.assertNotIn("2-12", report.replace(" ", ""))
        self.assertIn("Scheduled", report)
        self.assertNotIn("Marcador", report)


if __name__ == "__main__":
    unittest.main()
