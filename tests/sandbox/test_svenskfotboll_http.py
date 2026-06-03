import unittest

from sandbox.svenskfotboll_http.normalizers import (
    parse_competition_tree,
    parse_game_info_xml,
    parse_matches_widget,
    parse_standings_widget,
    search_competitions,
)


class SvenskfotbollNormalizersTests(unittest.TestCase):
    def test_parse_competition_tree_deduplicates_competitions(self):
        payload = {
            "competitions": [
                {
                    "category": "Allsvenskan herrar",
                    "associationId": 1,
                    "genderId": 2,
                    "ageCategoryId": 4,
                    "footballTypeId": 1,
                    "typeId": "Allsvenskan",
                    "comps": [{"id": 133348, "name": "Allsvenskan 2026", "url": "/go-to/?ftid=133348"}],
                },
                {
                    "category": "Duplicated group",
                    "associationId": 1,
                    "genderId": 2,
                    "ageCategoryId": 4,
                    "footballTypeId": 1,
                    "typeId": "Allsvenskan",
                    "comps": [{"id": 133348, "name": "Allsvenskan 2026", "url": "/go-to/?ftid=133348"}],
                },
            ]
        }

        competitions = parse_competition_tree(payload)

        self.assertEqual(len(competitions), 1)
        self.assertEqual(competitions[0]["competition_id"], "133348")
        self.assertIn("Allsvenskan herrar", competitions[0]["categories"])
        self.assertIn("Duplicated group", competitions[0]["categories"])

    def test_search_competitions_filters_by_query(self):
        competitions = [
            {"competition_id": "1", "name": "Allsvenskan 2026", "categories": ["Allsvenskan"], "association_ids": ["1"]},
            {"competition_id": "2", "name": "Ettan Norra", "categories": ["Ettan"], "association_ids": ["1"]},
        ]

        results = search_competitions(competitions, query="allsvenskan")

        self.assertEqual([item["competition_id"] for item in results], ["1"])

    def test_parse_standings_widget(self):
        html = """
        <table>
          <tr><td>Allsvenskan 2026</td></tr>
          <tr><td>Lag</td><td>S</td><td>D</td><td>P</td></tr>
          <tr><td><a href="https://www.svenskfotboll.se/widget-go-to/?flid=108445">IK Sirius FK</a></td><td>10</td><td>17</td><td>28</td></tr>
        </table>
        """

        standings = parse_standings_widget(html, 133348)

        self.assertEqual(standings["title"], "Allsvenskan 2026")
        self.assertEqual(standings["teams"][0]["team"], "IK Sirius FK")
        self.assertEqual(standings["teams"][0]["team_id"], "108445")
        self.assertEqual(standings["teams"][0]["points"], 28)

    def test_parse_matches_widget_extracts_match_id(self):
        html = """
        <table>
          <tr><td>Allsvenskan 2026: Kommande matcher</td></tr>
          <tr><td>Tid</td><td>Match</td></tr>
          <tr>
            <td>2026-07-03 19:00</td>
            <td><a href="https://www.svenskfotboll.se/widget-go-to/?scr=result&amp;fmid=6529914">IK Sirius FK - Mjällby AIF</a></td>
          </tr>
        </table>
        """

        fixtures = parse_matches_widget(html, 133348, result_rows=False)

        self.assertEqual(fixtures["matches"][0]["match_id"], "6529914")
        self.assertEqual(fixtures["matches"][0]["home"], "IK Sirius FK")
        self.assertEqual(fixtures["matches"][0]["away"], "Mjällby AIF")

    def test_parse_game_info_xml_summarizes_live_events(self):
        xml = """
        <game-info status="200">
          <game id="6812343" competition-id="133223" date="2026-06-03" start="18:30:00">
            <tournament id="133223" name="Dam U23 landskamp" />
            <teams>
              <team id="97728" short-name="Sverige" long-name="Sverige" home-team="true" />
              <team id="97651" short-name="Norge" long-name="Norge" home-team="false" />
            </teams>
            <status id="3" desc="HALFTIME" />
            <score home-team="2" away-team="0" />
            <stats home-corners="2" away-corners="2" home-red-cards="0" away-red-cards="1" />
            <events>
              <event id="1" type="G" type-desc="Goal" home-team="true" game-minute-for-web="6" />
              <event id="2" type="C" type-desc="Corner" home-team="false" game-minute-for-web="12" />
            </events>
          </game>
        </game-info>
        """

        game = parse_game_info_xml(xml)

        self.assertEqual(game["match_id"], "6812343")
        self.assertEqual(game["home"]["name"], "Sverige")
        self.assertEqual(game["event_summary"]["goals"], 1)
        self.assertEqual(game["event_summary"]["corners"], 1)
        self.assertEqual(game["stats"]["away-red-cards"], "1")


if __name__ == "__main__":
    unittest.main()

