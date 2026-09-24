"""Estado oficial del día: Statshub (unified_sport_matches) y Palloliitto (por fecha)."""
from __future__ import annotations

import unittest

from stats_providers.palloliitto.day_status import parse_day as parse_palloliitto
from stats_providers.sportradar_http.day_status import parse_day as parse_statshub


def _sr_match(match_id, home, away, status_id, name, *, result=(None, None), p1=None, uts=1790274600):
    return {"_id": match_id, "_dt": {"uts": uts}, "status": {"_id": status_id, "name": name},
            "teams": {"home": {"name": home}, "away": {"name": away}},
            "result": {"home": result[0], "away": result[1]},
            "periods": {"p1": {"home": p1[0], "away": p1[1]}} if p1 else None}


STATSHUB_DAY = {"doc": [{"data": {"sport": {"realcategories": [
    {"name": "International Youth", "tournaments": [
        {"name": "U21 EURO, Qualification, Group A", "_gender": "men", "matches": [
            _sr_match(58208351, "San Marino", "Kosovo", 6, "1st half", result=(0, 1), p1=(0, 1))]}]},
    {"name": "International", "tournaments": [
        {"name": "Africa Cup of Nations, Qualification", "_gender": "men", "matches": [
            _sr_match(1, "Congo DR", "Equatorial Guinea", 31, "Halftime", result=(1, 0), p1=(1, 0)),
            _sr_match(2, "Namibia", "Congo Republic", 100, "Ended", result=(1, 0), p1=(0, 0))]}]},
    {"name": "Sweden", "tournaments": [
        {"name": "Elitettan", "_gender": "women", "matches": [
            _sr_match(3, "Enskede IK", "KIF Orebro", 0, "Not started")]}]},
    {"name": "Simulated Reality League", "tournaments": [
        {"name": "SRL Club Friendlies", "_gender": "men", "matches": [
            _sr_match(4, "Kosovo SRL", "Republic of Ireland Srl", 100, "Ended", result=(2, 0))]}]},
]}}}]}

PALLOLIITTO_DAY = [
    {"match_id": "10", "team_A_name": "JyTy", "team_B_name": "Åbo CF", "status": "Break",
     "live_period": "1", "fs_A": "1", "fs_B": "0", "hts_A": "1", "hts_B": "0", "live_minutes": 45,
     "date": "2026-09-24", "time": "18:30:00", "time_zone_offset": "+0300",
     "competition_name": "Länsi Jalkapallo 2026", "category_name": "Kolmonen"},
    {"match_id": "11", "team_A_name": "EPS", "team_B_name": "Hercules-j", "status": "Played",
     "live_period": "2", "fs_A": "1", "fs_B": "1", "hts_A": "0", "hts_B": "0",
     "date": "2026-09-24", "time": "09:00:00", "time_zone_offset": "+0300",
     "competition_name": "SPL Huuhkaja-Helmariliiga 2026", "category_name": "P13 Huuhkajaliiga"},
    {"match_id": "12", "team_A_name": "SeMi", "team_B_name": "Virkiä", "status": "Live",
     "live_period": "2", "fs_A": "4", "fs_B": "0", "hts_A": "2", "hts_B": "0", "live_minutes": 67,
     "date": "2026-09-24", "time": "17:00:00", "time_zone_offset": "+0300",
     "competition_name": "Länsi Jalkapallo 2026", "category_name": "T18 Kakkonen"},
    {"match_id": "13", "team_A_name": "PK-35", "team_B_name": "HJK", "status": "Fixture",
     "live_period": "-1", "fs_A": "", "fs_B": "", "hts_A": "", "hts_B": "",
     "date": "2026-09-24", "time": "19:00:00", "time_zone_offset": "+0300",
     "competition_name": "Kansallinen Liiga 2026", "category_name": "Naisten Kansallinen Liiga"},
]


class StatshubDayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.by_id = {m.match_id: m for m in parse_statshub(STATSHUB_DAY)}

    def test_phases_scores_and_halftime(self) -> None:
        live, halftime, ended = self.by_id["58208351"], self.by_id["1"], self.by_id["2"]
        self.assertEqual((live.phase, live.home_score, live.away_score), ("live", 0, 1))
        self.assertIsNone(live.ht_home_score)  # 1er tiempo en juego: p1 todavía no es el entretiempo
        self.assertEqual(live.scheduled_at, "2026-09-24T18:30:00+00:00")
        self.assertEqual((halftime.phase, halftime.minute, halftime.ht_home_score), ("halftime", "HT", 1))
        self.assertEqual((ended.phase, ended.minute, ended.ht_home_score, ended.home_score), ("ended", "FT", 0, 1))

    def test_category_and_simulated_matches(self) -> None:
        self.assertIn("U21", self.by_id["58208351"].competition_name)
        self.assertEqual(self.by_id["3"].competition_name, "Elitettan Women")
        self.assertNotIn("4", self.by_id)  # SRL = simulado

    def test_garbage_is_empty(self) -> None:
        self.assertEqual(parse_statshub({}), [])


class PalloliittoDayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.by_id = {m.match_id: m for m in parse_palloliitto(PALLOLIITTO_DAY)}

    def test_break_is_halftime_and_played_is_final(self) -> None:
        halftime = self.by_id["10"]
        self.assertEqual((halftime.phase, halftime.minute, halftime.ht_home_score), ("halftime", "HT", 1))
        self.assertEqual(halftime.scheduled_at, "2026-09-24T18:30:00+03:00")
        second_half = self.by_id["12"]
        self.assertEqual((second_half.phase, second_half.minute, second_half.ht_home_score),
                         ("live", "67'", 2))
        self.assertEqual((self.by_id["11"].phase, self.by_id["11"].minute), ("ended", "FT"))
        self.assertEqual((self.by_id["13"].phase, self.by_id["13"].home_score), ("scheduled", None))

    def test_youth_and_women_categories_are_marked(self) -> None:
        self.assertTrue(self.by_id["11"].competition_name.endswith("U13"))
        self.assertTrue(self.by_id["12"].competition_name.endswith("U18 Women"))
        self.assertNotIn("U", self.by_id["10"].competition_name.split()[-1])
        from core.match_identity import age_groups, is_womens

        self.assertEqual(age_groups(self.by_id["11"].competition_name), {"u13"})
        self.assertTrue(is_womens(self.by_id["13"].competition_name))  # "Naisten"


if __name__ == "__main__":
    unittest.main()
