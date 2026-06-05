from __future__ import annotations

import unittest

from monitors.match_analytics import build_analytics, render_analytics
from monitors.peak_model import LeagueModel, PastMatch, TeamStats


def _t(tid, pos, gfh, gah, gfa, gaa, ph=3, pa=2):
    return TeamStats(team_id=tid, name=tid, position=pos, played=ph + pa,
                     played_home=ph, played_away=pa,
                     gf_home=gfh, ga_home=gah, gf_away=gfa, ga_away=gaa)


def _model():
    teams = {
        "H": _t("H", 1, 9, 3, 4, 2),
        "A": _t("A", 4, 2, 6, 1, 9),
        "M1": _t("M1", 2, 5, 5, 4, 5),
        "M2": _t("M2", 3, 4, 4, 3, 6),
    }
    matches = [
        PastMatch(date="2026-05-20", home_id="H", away_id="A", gh=3, ga=0),
        PastMatch(date="2026-04-10", home_id="A", away_id="H", gh=1, ga=2),
        PastMatch(date="2026-05-25", home_id="H", away_id="M1", gh=2, ga=2),
        PastMatch(date="2026-05-28", home_id="M2", away_id="A", gh=4, ga=0),
    ]
    return LeagueModel(name="T", teams=teams, matches=matches)


class BuildAnalyticsTests(unittest.TestCase):
    def test_positions_and_league_size(self) -> None:
        a = build_analytics(_model(), "H", "A", "HomeFC", "AwayFC")
        self.assertEqual(a.home_position, 1)
        self.assertEqual(a.away_position, 4)
        self.assertEqual(a.n_teams, 4)

    def test_team_goal_averages(self) -> None:
        a = build_analytics(_model(), "H", "A", "HomeFC", "AwayFC")
        # H: (9+4)/5 = 2.6 scored, (3+2)/5 = 1.0 conceded, home 9/3=3.0
        self.assertAlmostEqual(a.home_goals.scored_avg, 2.6)
        self.assertAlmostEqual(a.home_goals.conceded_avg, 1.0)
        self.assertAlmostEqual(a.home_goals.scored_home_avg, 3.0)
        self.assertAlmostEqual(a.away_goals.scored_avg, 0.6)

    def test_league_averages(self) -> None:
        a = build_analytics(_model(), "H", "A", "HomeFC", "AwayFC")
        # total gf = (9+4)+(2+1)+(5+4)+(4+3)=32 ; total pj = 5*4=20 -> 1.6
        self.assertAlmostEqual(a.league_avg, 1.6)
        # home gf = 9+2+5+4=20 ; home pj = 3*4=12 -> 1.6667
        self.assertAlmostEqual(a.league_home_avg, 20 / 12)

    def test_form_and_h2h(self) -> None:
        a = build_analytics(_model(), "H", "A", "HomeFC", "AwayFC")
        # H most recent: 2026-05-25 draw vs M1, then 2026-05-20 win vs A, then 2026-04-10 win
        self.assertEqual(a.home_form[0], "D")
        self.assertIn("W", a.home_form)
        # H2H H vs A: two matches, most recent first
        self.assertEqual(len(a.h2h), 2)
        self.assertEqual(a.h2h[0].date, "2026-05-20")

    def test_render_contains_sections_and_escapes(self) -> None:
        a = build_analytics(_model(), "H", "A", "Home&Co", "Away")
        lines = render_analytics(a, "Home&Co", "Away", escape=lambda s: s.replace("&", "&amp;"))
        text = "\n".join(lines)
        self.assertIn("Análisis pre-match", text)
        self.assertIn("Posición", text)
        self.assertIn("Forma", text)
        self.assertIn("Liga:", text)
        self.assertIn("H2H", text)
        self.assertIn("Home&amp;Co", text)  # escape applied

    def test_missing_team_safe(self) -> None:
        a = build_analytics(_model(), "ZZZ", "A", "Ghost", "AwayFC")
        self.assertIsNone(a.home_position)
        lines = render_analytics(a, "Ghost", "AwayFC")
        self.assertTrue(any("Forma" in l for l in lines))


if __name__ == "__main__":
    unittest.main()
