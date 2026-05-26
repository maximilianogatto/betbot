from __future__ import annotations

import json
import unittest

from sandbox.sportradar_http.bot_ready.provider import build_live_state_document


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


if __name__ == "__main__":
    unittest.main()
