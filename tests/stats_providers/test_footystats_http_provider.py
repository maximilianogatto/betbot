from __future__ import annotations

import asyncio
import unittest

from core.stats_models import MatchIdentityCandidate
from stats_providers.footystats_http.normalizers import (
    decode_public_match_id,
    discover_public_leagues,
    normalize_public_fixtures,
    normalize_public_standings,
)
from stats_providers.footystats_http.provider import FootyStatsHttpStatsProvider


HOME_HTML = """
<a href='/australia/northern-nsw-npl'>Northern NSW NPL</a>
<a href='/australia/northern-nsw-npl'>Northern NSW NPL</a>
<a href='/clubs/not-a-league-1'>Club</a>
"""

LEAGUE_HTML = """
<a href='/clubs/valentine-fc-5515'><span itemprop='name'>Valentine</span></a>
<a href='/clubs/edgeworth-eagles-fc-5516'><span itemprop='name'>Edgeworth Eagles</span></a>
<script>
var mh_matchData = [
  {"id":8439330,"matchHomeID":5515,"matchAwayID":5516,"status":"incomplete","date":1781937000},
];
</script>
<table class='full-league-table table-sort'>
<tbody><tr class=''><td class='position bold'><span>1</span></td>
<td class='team borderRightContent'><a href='/clubs/valentine-fc-5515' data-team-id='5515'>Valentine FC</a></td>
<td class='mp'>13</td><td class='win'>9</td><td class='draw'>3</td><td class='loss'>1</td>
<td class='gf'>36</td><td class='ga'>17</td><td class='gd'>+19</td><td class='points bold'>30</td>
<td class='ppg'><div>2.31</div></td><td class='cs'>23%</td><td class='btts'>69%</td>
<td class='over25'>77%</td><td class='avg bold'>4.08</td></tr></tbody>
</table>
"""


class FakeFootyStatsClient:
    def get_public_html(self, path: str) -> str:
        return HOME_HTML if path == "/" else LEAGUE_HTML

    def get_live_scores(self):
        return [{"match_id": 8439330, "team_a_score": "2", "team_b_score": "1", "minute": "70"}]

    def close(self) -> None:
        return None


class FootyStatsProductionNormalizerTests(unittest.TestCase):
    def test_discovers_public_league_and_ignores_club_link(self) -> None:
        leagues = discover_public_leagues(HOME_HTML)
        self.assertEqual(len(leagues), 1)
        self.assertEqual(leagues[0]["league_id"], "australia/northern-nsw-npl")

    def test_normalizes_fixture_and_standing(self) -> None:
        fixtures = normalize_public_fixtures(LEAGUE_HTML, "australia/northern-nsw-npl")
        standings = normalize_public_standings(LEAGUE_HTML)

        self.assertEqual(fixtures[0]["home"], "Valentine")
        self.assertEqual(fixtures[0]["away"], "Edgeworth Eagles")
        self.assertIn("valentine-fc-vs-edgeworth-eagles-fc", fixtures[0]["provider_match_id"])
        self.assertEqual(standings["tables"][0]["rows"][0]["points"], 30)

    def test_decodes_public_provider_match_id(self) -> None:
        path, match_id = decode_public_match_id("public:/australia/a-vs-b-h2h-stats#7")
        self.assertEqual(path, "/australia/a-vs-b-h2h-stats")
        self.assertEqual(match_id, "7")


class FootyStatsProductionProviderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FootyStatsHttpStatsProvider(client=FakeFootyStatsClient())

    def test_discovers_league_and_lists_fixture(self) -> None:
        leagues = asyncio.run(self.provider.search_leagues(country_name="Australia"))
        fixtures = asyncio.run(self.provider.list_fixtures(leagues[0].league_id))

        self.assertEqual(leagues[0].league_name, "Northern NSW NPL")
        self.assertEqual(fixtures[0].home, "Valentine")
        self.assertEqual(fixtures[0].away, "Edgeworth Eagles")

    def test_resolves_fixture_and_builds_direct_live_report(self) -> None:
        link = asyncio.run(
            self.provider.resolve_match(
                MatchIdentityCandidate(
                    home="Valentine FC",
                    away="Edgeworth Eagles",
                    scheduled_at="2026-06-20T03:50:00+00:00",
                ),
                league_id="australia/northern-nsw-npl",
            )
        )
        self.assertIsNotNone(link)

        report = asyncio.run(self.provider.build_match_report(link.stats_match_id))

        self.assertIn("Valentine Fc vs Edgeworth Eagles Fc", report.markdown)
        self.assertIn("Live: 2-1", report.markdown)


if __name__ == "__main__":
    unittest.main()
