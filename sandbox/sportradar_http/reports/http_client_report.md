# Sportradar HTTP Client Report

- Generated at: `2026-05-26T19:31:35.828084+00:00`
- Snapshot schema: `1`
- Inputs: `{'sport_id': 1, 'date': '2026-05-26', 'match_id': 61624678, 'season_id': 130805, 'team_id': 2885}`
- Token expiration: `2026-05-27T06:17:04+00:00`

## Successful HTTP Replay

- `fixtures` bytes=424426 queryUrl=`unified_sport_matches/1/2026-05-26/0` event=`unified_sport_matches` data_type=`dict` counts=`{'sport': 6}`
- `fixture_markets` bytes=150398 queryUrl=`unified_sport_matches_markets/1/2026-05-26/0` event=`unified_sport_matches_markets` data_type=`dict` counts=`{'matches': 21}`
- `match_odds` bytes=137 queryUrl=`match_markets/61624678` event=`match_markets` data_type=`dict` counts=`{'markets': 0}`
- `standings` bytes=24574 queryUrl=`stats_season_tables/130805` event=`stats_season_tables` data_type=`dict` counts=`{'start': 6, 'end': 6, 'tables': 1}`
- `formtable` bytes=54518 queryUrl=`stats_formtable/130805` event=`stats_formtable` data_type=`dict` counts=`{'matchtype': 4, 'tabletype': 2, 'season': 12, 'teams': 20}`
- `team_lastx` bytes=7258 queryUrl=`stats_team_lastx/2885/5` event=`stats_team_lastx` data_type=`dict` counts=`{'team': 15, 'matches': 5, 'tournaments': 1, 'uniquetournaments': 1, 'realcategories': 1}`
- `team_streaks` bytes=2818 queryUrl=`stats_team_streaks/2885` event=`stats_team_streaks` data_type=`dict` counts=`{'team': 15, 'lastmatchesform': 3, 'streaks': 1}`

## Blocked Request Example

- Status: `200`
- Body bytes: `149`
- Validation: `{'ok': False, 'status_code': 200, 'endpoint_key': 'unified_sport_matches', 'blocked': True, 'expired': False, 'empty': False, 'invalid_json': False, 'http_error': False, 'reason': 'blocked_payload'}`

## Refresh Example

- Refreshed: `True`
- Token expiration: `2026-05-27T20:41:04+00:00`
- Bootstrap fetch count: `33`
- Payload summary: `{'queryUrl': 'match_markets/61624678', 'doc_event': 'match_markets', 'top_level_keys': ['doc', 'queryUrl'], 'data_type': 'dict', 'data_keys': ['markets'], 'data_counts': {'markets': 0}}`

## Client Metrics

```json
{
  "total_requests": 7,
  "success_count": 7,
  "retry_count": 0,
  "refresh_count": 0,
  "blocked_count": 0,
  "expired_count": 0,
  "empty_count": 0,
  "invalid_json_count": 0,
  "http_error_count": 0,
  "endpoint_timings_ms": {
    "unified_sport_matches": [
      1376.2
    ],
    "unified_sport_matches_markets": [
      2319.68
    ],
    "match_markets": [
      13020.32
    ],
    "stats_season_tables": [
      1146.59
    ],
    "stats_formtable": [
      596.15
    ],
    "stats_team_lastx": [
      677.43
    ],
    "stats_team_streaks": [
      719.99
    ]
  },
  "endpoint_timing_summary": {
    "unified_sport_matches": {
      "count": 1,
      "min_ms": 1376.2,
      "max_ms": 1376.2,
      "avg_ms": 1376.2
    },
    "unified_sport_matches_markets": {
      "count": 1,
      "min_ms": 2319.68,
      "max_ms": 2319.68,
      "avg_ms": 2319.68
    },
    "match_markets": {
      "count": 1,
      "min_ms": 13020.32,
      "max_ms": 13020.32,
      "avg_ms": 13020.32
    },
    "stats_season_tables": {
      "count": 1,
      "min_ms": 1146.59,
      "max_ms": 1146.59,
      "avg_ms": 1146.59
    },
    "stats_formtable": {
      "count": 1,
      "min_ms": 596.15,
      "max_ms": 596.15,
      "avg_ms": 596.15
    },
    "stats_team_lastx": {
      "count": 1,
      "min_ms": 677.43,
      "max_ms": 677.43,
      "avg_ms": 677.43
    },
    "stats_team_streaks": {
      "count": 1,
      "min_ms": 719.99,
      "max_ms": 719.99,
      "avg_ms": 719.99
    }
  }
}
```

## Notes

- Browser is used only for bootstrap/refresh.
- Successful examples use pure HTTP replay after bootstrap.
- The blocked example intentionally omits replay headers to verify detection.
