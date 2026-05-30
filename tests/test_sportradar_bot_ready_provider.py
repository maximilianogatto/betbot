from __future__ import annotations

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from stats_providers.sportradar_http.engine.bot_ready.provider import (
    BotReadyMatchRequest,
    BotReadyRuntimeConfig,
    BotReadyTournamentRequest,
    SportradarBotReadyProvider,
    build_live_state_document,
)


class SportradarSessionPreRefreshTests(unittest.TestCase):
    def _provider_with_fake_manager(self, tmp: str) -> tuple[SportradarBotReadyProvider, SimpleNamespace]:
        state_path = Path(tmp) / "state.json"
        state_path.write_text("{}")
        config = BotReadyRuntimeConfig(
            session_state_path=state_path,
            bootstrap_profile_dir=Path(tmp) / "profile",
        )
        provider = SportradarBotReadyProvider(config)
        fake_manager = SimpleNamespace(refreshes=0)

        def refresh() -> str:
            fake_manager.refreshes += 1
            return "NEW_STATE"

        fake_manager.refresh_session = refresh
        provider.session_manager = fake_manager
        return provider, fake_manager

    def test_ensure_fresh_session_skips_when_token_has_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider, manager = self._provider_with_fake_manager(tmp)
            token = SimpleNamespace(is_expired=lambda: False, seconds_until_expiration=lambda: 99999.0)
            state = SimpleNamespace(signed_token=token)
            with patch("stats_providers.sportradar_http.engine.bot_ready.provider.load_session_state", return_value=state):
                refreshed = provider.ensure_fresh_session(min_ttl_seconds=3600.0)
            self.assertFalse(refreshed)
            self.assertEqual(manager.refreshes, 0)

    def test_ensure_fresh_session_refreshes_when_expiring_soon(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            provider, manager = self._provider_with_fake_manager(tmp)
            token = SimpleNamespace(is_expired=lambda: False, seconds_until_expiration=lambda: 60.0)
            state = SimpleNamespace(signed_token=token)
            with patch("stats_providers.sportradar_http.engine.bot_ready.provider.load_session_state", return_value=state), patch(
                "stats_providers.sportradar_http.engine.bot_ready.provider.save_session_state"
            ):
                refreshed = provider.ensure_fresh_session(min_ttl_seconds=3600.0)
            self.assertTrue(refreshed)
            self.assertEqual(manager.refreshes, 1)


class SportradarBotReadyProviderTests(unittest.TestCase):
    def test_build_live_state_document_is_compact_and_serializable(self) -> None:
        payloads = {
            "match_info": {
                "doc": [
                    {
                        "data": {
                            "match": {
                                "_id": 10,
                                "_seasonid": 99,
                                "teams": {"home": {"uid": 1, "name": "A"}, "away": {"uid": 2, "name": "B"}},
                                "result": {"home": 1, "away": 0},
                            }
                        }
                    }
                ]
            },
            "match_timeline": {
                "doc": [
                    {
                        "data": {
                            "match": {"result": {"home": 1, "away": 0}, "timeinfo": {"running": True, "played": "1800"}},
                            "events": [{"_id": "e1", "type": "score_change", "name": "Goal", "team": "home", "time": 12}],
                        }
                    }
                ]
            },
            "match_timelinedelta": {"doc": [{"data": {"match": {}, "events": []}}]},
            "match_situation": {
                "doc": [
                    {
                        "data": {
                            "data": [
                                {
                                    "time": 1,
                                    "home": {"dangerous": 2, "dangerouscount": 1},
                                    "away": {"dangerous": 1, "dangerouscount": 1},
                                }
                            ]
                        }
                    }
                ]
            },
        }

        document = build_live_state_document(match_id=10, payloads=payloads, errors={})

        self.assertEqual(document["kind"], "live_match_state")
        self.assertTrue(document["feature_quality"]["has_timeline"])
        self.assertEqual(document["metadata"]["home"]["name"], "A")
        self.assertEqual(document["live_state"]["raw_event_count"], 1)
        self.assertEqual(len(document["raw_refs"]), 4)
        json.dumps(document)

    def test_match_report_package_includes_match_intelligence(self) -> None:
        provider = SportradarBotReadyProvider()

        with (
            patch.object(provider, "_client", return_value=_FakeClient()),
            patch.object(provider, "_persist_state"),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.fetch_match_payloads", return_value=({}, {})),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.build_match_snapshot", return_value=_match_snapshot_fixture()),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.build_match_features", return_value=_match_features_fixture()),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.render_match_report", return_value="# technical report\n"),
        ):
            package = provider.get_match_report(BotReadyMatchRequest(match_id=61624678))

        self.assertEqual(package["kind"], "match_report")
        self.assertIn("intelligence", package)
        self.assertEqual(package["intelligence"]["match_id"], 61624678)
        self.assertIn("Team A vs Team C", package["intelligence_markdown"])

    def test_tournament_navigation_package_lists_fixtures(self) -> None:
        provider = SportradarBotReadyProvider()

        with (
            patch.object(provider, "_client", return_value=_FakeClient()),
            patch.object(provider, "_persist_state"),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.get_config_tree_mini", return_value=_config_tree_fixture()),
            patch("stats_providers.sportradar_http.engine.bot_ready.provider.get_tournament_fixtures", return_value=_fixtures_fixture()),
        ):
            package = provider.get_tournament_navigation(BotReadyTournamentRequest(sport_id=1, tournament_id=18340))

        self.assertEqual(package["kind"], "tournament_navigation")
        self.assertEqual(package["snapshot"]["resolved_tournament"]["season_id"], 138964)
        self.assertEqual(package["fixtures"][0]["match_id"], 7001)
        self.assertIn("South Australia NPL, Women", package["report_markdown"])
        json.dumps(package)


class _FakeClient:
    state = None

    def metrics_json(self) -> dict:
        return {"total_requests": 0}


def _match_snapshot_fixture() -> dict:
    return {
        "metadata": {
            "match_id": 61624678,
            "home": {"uid": 10, "name": "Team A"},
            "away": {"uid": 20, "name": "Team C"},
            "competition": {"name": "Example League"},
            "kickoff": {"iso_utc": "2026-06-01T20:00:00+00:00"},
            "status": {"name": "Not started"},
            "score": {"home": None, "away": None},
        },
        "team_form": {"home": {"form": ["W"], "recent_points": 3, "matches": []}, "away": {"form": ["L"], "recent_points": 0, "matches": []}},
        "team_scoring": {},
        "h2h": {"summary": {}, "matches": []},
        "injuries": {"home": [], "away": []},
        "players": {"home": {}, "away": {}},
        "live_state": {},
        "feature_quality": {},
    }


def _match_features_fixture() -> dict:
    return {"values": {"attack_strength_home": 1.0, "attack_strength_away": 0.8}}


def _config_tree_fixture() -> dict:
    return {
        "doc": [
            {
                "data": [
                    {
                        "_id": 1,
                        "_sid": 1,
                        "name": "Soccer",
                        "realcategories": [
                            {
                                "_id": 34,
                                "_sid": 1,
                                "_rcid": 34,
                                "name": "Australia",
                                "cc": {"a2": "au", "name": "Australia"},
                                "tournaments": [
                                    {
                                        "_id": 46533,
                                        "_sid": 1,
                                        "_rcid": 34,
                                        "_tid": 46533,
                                        "_utid": 18340,
                                        "name": "South Australia NPL, Women",
                                        "seasonid": 138964,
                                        "currentseason": 138964,
                                        "roundbyround": True,
                                    }
                                ],
                            }
                        ],
                    }
                ]
            }
        ],
        "queryUrl": "/bet365/en/Etc:UTC/gismo/config_tree_mini/67/0/1",
    }


def _fixtures_fixture() -> dict:
    return {
        "doc": [
            {
                "data": {
                    "matches": [
                        {
                            "_id": 7001,
                            "time": {"uts": 1781338200, "date": "13/06/26", "time": "08:10", "tz": "UTC"},
                            "teams": {
                                "home": {"_id": 100, "uid": 100, "name": "Home FC"},
                                "away": {"_id": 200, "uid": 200, "name": "Away FC"},
                            },
                            "result": {"home": None, "away": None, "winner": None},
                        }
                    ]
                }
            }
        ],
        "queryUrl": "/bet365/en/Etc:UTC/gismo/stats_season_fixtures2/138964",
    }


if __name__ == "__main__":
    unittest.main()
