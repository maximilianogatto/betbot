from __future__ import annotations

import asyncio
import unittest

from core.stats_models import MatchIdentityCandidate
from stats_providers.footystats_http.normalizers import (
    decode_public_match_id,
    discover_public_leagues,
    normalize_public_fixtures,
    normalize_public_standings,
    normalize_public_match_h2h,
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
        if "devonport-vs-launceston" in path:
            return MOCK_H2H_HTML
        return HOME_HTML if path == "/" else LEAGUE_HTML

    def get_live_scores(self):
        return [{"match_id": 8439330, "team_a_score": "2", "team_b_score": "1", "minute": "70"}]

    def close(self) -> None:
        return None


MOCK_H2H_HTML = """
<section class='stat-group stat-box h2h-widget-neo'>
<div class='title-bar'><h2>Head to Head Statistics</h2></div>
<div class='inner-content'>
<div class='row cf'>
<div class='fl ac teamA pr w25'>
<a href='/clubs/devonport-city-strikers-fc-ii-7526'>Devonport City II</a>
</div>
<div class='fl ac teamB pr w25'>
<a href='/clubs/launceston-city-fc-ii-7584'>Launceston City II</a>
</div>
</div>
<p class='h2h-trailing-text'>Devonport City II vs Launceston City II's head to head record shows that in the previous 30 meetings, Devonport City II has won 23 times, Launceston City II has won 6 times, and 1 ended in a draw. Devonport City II scored 105 goals and Launceston City II scored 43 goals in these matches.</p>
<div class='stat-grid w90 rw100 rpnone rmt1e'>
<div class="grid-item has-indicator great overview pr zi1"><div class="stat-strong">87%<span>Over 1.5</span></div><div class="stat-text">26 / 30 matches</div></div>
<div class="grid-item has-indicator great overview pr zi1"><div class="stat-strong">87%<span>Over 2.5</span></div><div class="stat-text">26 / 30 matches</div></div>
<div class="grid-item has-indicator good overview pr zi1"><div class="stat-strong">67%<span>BTTS</span></div><div class="stat-text">20 / 30 matches</div></div>
<div class="grid-item has-indicator poor overview pr zi1"><div class="stat-strong">30%<span>Clean Sheets</span></div><div class="stat-text">Devonport City II</div></div>
<div class="grid-item has-indicator poor overview pr zi1"><div class="stat-strong">3%<span>Clean Sheets</span></div><div class="stat-text">Launceston City II</div></div>
</div>
</div>
<div class='sliding-fixtures pr'>
<div class='inner'>
<a href='#' class='fixture changeH2HDataButton_neo' data-zzzz='8471443' data-z='7584' data-zz='7526'><time class='timezone-convert-match-h2h-neo' datetime='2026-04-18T10:00'>Apr 18, 2026</time><div class='team  black'>Launceston City II <span>0</span></div><div class='team winner black'>Devonport City II <span>1</span></div></a>
<a href='#' class='fixture changeH2HDataButton_neo' data-zzzz='7843089' data-z='7584' data-zz='7526'><time class='timezone-convert-match-h2h-neo' datetime='2025-08-16T03:15'>Aug 16, 2025</time><div class='team  black'>Launceston City II <span>1</span></div><div class='team winner black'>Devonport City II <span>3</span></div></a>
</div>
</div>
</section>

<h3><a href='/clubs/devonport-city-strikers-fc-ii-7526'>Devonport City Strikers FC II</a></h3>
<p>League Pos. <span class='semi-bold'>2</span> / 8</p>
<div class='neo-border-all'>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Overall</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run win'>W</li><li class='form-run win'>W</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">2.50</div></div></div>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Home</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run win'>W</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">3.00</div></div></div>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Away</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run win'>W</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">2.00</div></div></div>
</div>

<h3><a href='/clubs/launceston-city-fc-ii-7584'>Launceston City FC II</a></h3>
<p>League Pos. <span class='semi-bold'>5</span> / 8</p>
<div class='neo-border-all'>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Overall</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run loss'>L</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">1.00</div></div></div>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Home</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run win'>W</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">1.50</div></div></div>
<div class='section1 cf bbox'><div class='col1 dark-gray semi-bold fl ac'>Away</div><div class='col2 dark-gray fl ac'><ul class="form-run"><li class='form-run loss'>L</li></ul></div><div class='col3 dark-gray fl ac'><div class="form-box">0.50</div></div></div>
</div>

<table class='miniTableNeo table-sort'>
<tbody>
<tr><td class='position'>2</td><td><a href='/clubs/devonport-city-strikers-fc-ii-7526'>Devonport City II</a></td><td>4</td><td>75%</td><td>20</td><td>8</td><td>12</td><td>10</td><td>7.00</td></tr>
<tr><td class='position'>5</td><td><a href='/clubs/launceston-city-fc-ii-7584'>Launceston City II</a></td><td>4</td><td>50%</td><td>8</td><td>5</td><td>3</td><td>6</td><td>3.25</td></tr>
</tbody>
</table>

<table class='miniTableNeo table-sort'>
<tbody>
<tr><td class='position'>2</td><td><a href='/clubs/devonport-city-strikers-fc-ii-7526'>Devonport City II</a></td><td>4</td><td>75%</td><td>12</td><td>2</td><td>10</td><td>10</td><td>3.50</td></tr>
<tr><td class='position'>5</td><td><a href='/clubs/launceston-city-fc-ii-7584'>Launceston City II</a></td><td>5</td><td>20%</td><td>2</td><td>7</td><td>-5</td><td>4</td><td>1.80</td></tr>
</tbody>
</table>

<table class='miniTableNeo table-sort'>
<tbody>
<tr><td class='position'>2</td><td><a href='/clubs/devonport-city-strikers-fc-ii-7526'>Devonport City II</a></td><td>8</td><td>75%</td><td>32</td><td>10</td><td>22</td><td>20</td><td>5.25</td></tr>
<tr><td class='position'>5</td><td><a href='/clubs/launceston-city-fc-ii-7584'>Launceston City II</a></td><td>9</td><td>33%</td><td>10</td><td>12</td><td>-2</td><td>10</td><td>2.44</td></tr>
</tbody>
</table>

<table class='w100 stats-to-odds-table'>
<tbody>
<tr><td>Devonport City II Win</td><td>-</td><td>75%</td></tr>
<tr><td>Launceston City II Win</td><td>-</td><td>20%</td></tr>
<tr><td>Draw</td><td>-</td><td>23%</td></tr>
<tr><td>Over 2.5</td><td>-</td><td>70%</td></tr>
<tr><td>BTTS</td><td>-</td><td>60%</td></tr>
</tbody>
</table>
"""


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

    def test_describe_league_accepts_url_and_locale_prefix(self) -> None:
        canonical = "australia/northern-nsw-npl"
        for reference in (
            canonical,
            f"https://footystats.org/{canonical}",
            f"es/{canonical}",
            f"https://footystats.org/es/{canonical}",
        ):
            option = asyncio.run(self.provider.describe_league(reference))
            self.assertIsNotNone(option, reference)
            self.assertEqual(option.league_id, canonical, reference)
            self.assertEqual(option.league_name, "Northern NSW NPL", reference)

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


class FootyStatsH2HNormalizerAndReportTests(unittest.TestCase):
    def test_normalize_public_match_h2h(self) -> None:
        data = normalize_public_match_h2h(MOCK_H2H_HTML)
        self.assertEqual(data["home"]["name"], "Devonport City Strikers FC II")
        self.assertEqual(data["home"]["id"], "7526")
        self.assertEqual(data["home"]["league_pos"], 2)
        self.assertEqual(data["home"]["league_pos_total"], 8)
        self.assertEqual(data["home"]["stats"]["overall"]["ppg"], 2.50)
        self.assertEqual(data["home"]["stats"]["overall"]["form"], "WW")
        
        self.assertEqual(data["away"]["name"], "Launceston City FC II")
        self.assertEqual(data["away"]["id"], "7584")
        self.assertEqual(data["away"]["league_pos"], 5)
        self.assertEqual(data["away"]["stats"]["overall"]["ppg"], 1.00)
        self.assertEqual(data["away"]["stats"]["overall"]["form"], "L")
        
        # Mini tables
        self.assertEqual(data["mini_tables"]["home"]["overall"]["pos"], 2)
        self.assertEqual(data["mini_tables"]["home"]["overall"]["pts"], 20)
        self.assertEqual(data["mini_tables"]["home"]["overall"]["gf"], 32)
        self.assertEqual(data["mini_tables"]["home"]["overall"]["ga"], 10)
        
        self.assertEqual(data["mini_tables"]["away"]["overall"]["pos"], 5)
        self.assertEqual(data["mini_tables"]["away"]["overall"]["pts"], 10)
        
        # Markets
        self.assertEqual(data["markets"]["draw"]["value"], "23")
        self.assertEqual(data["markets"]["over_2.5"]["value"], "70")
        
        # Fixtures
        self.assertEqual(len(data["fixtures"]), 2)
        self.assertEqual(data["fixtures"][0]["home"], "Launceston City II")
        self.assertEqual(data["fixtures"][0]["home_score"], 0)
        self.assertEqual(data["fixtures"][0]["away_score"], 1)
        self.assertEqual(data["fixtures"][0]["away"], "Devonport City II")
        
        # H2H Tendencies
        self.assertEqual(data["h2h_tendencies"]["over_1.5"], 87)
        self.assertEqual(data["h2h_tendencies"]["over_2.5"], 87)
        self.assertEqual(data["h2h_tendencies"]["btts"], 67)
        self.assertEqual(data["h2h_tendencies"]["home_clean_sheets"], 30)
        self.assertEqual(data["h2h_tendencies"]["away_clean_sheets"], 3)
        
        # H2H summary
        self.assertIn("Devonport City II vs Launceston City II", data["h2h_summary"])

    def test_build_match_report_rich(self) -> None:
        provider = FootyStatsHttpStatsProvider(client=FakeFootyStatsClient())
        report = asyncio.run(provider.build_match_report("public:/australia/devonport-vs-launceston-h2h-stats#8471443"))
        
        self.assertIn("Devonport City Strikers FC II vs Launceston City FC II", report.title)
        self.assertIn("2.50 PPG (WW) vs 1.00 PPG (L)", report.markdown)
        self.assertIn("Launceston City II 0-1 Devonport City II", report.markdown)
        self.assertIn("Devonport City Strikers FC II=4.00 | Launceston City FC II=1.11", report.markdown)
        self.assertIn("Devonport City Strikers FC II home=5.00 | Launceston City FC II away=0.40", report.markdown)
        self.assertIn("BTTS: 67% (H2H) | 60% (Temporada)", report.markdown)
        self.assertIn("Over 2.5: 87% (H2H) | 70% (Temporada)", report.markdown)
        self.assertIn("Table: 2° (20 pts, 8P) vs 5° (10 pts, 9P)", report.markdown)


if __name__ == "__main__":
    unittest.main()
