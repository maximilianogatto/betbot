# Sportradar League Pipeline Report

- Generated at: `2026-05-26T19:55:01.614666+00:00`
- Inputs: `{'sport_id': 1, 'tournament_id': 8, 'season_id': 130805, 'season_id_source': 'explicit'}`
- Teams: `20`
- Fixtures normalized: `383`
- Injuries normalized: `50`

## League Summary

- Matches played: `380`
- Goals per match: `2.695`
- BTTS rate: `0.565789`
- Clean sheet rate: `0.434211`
- Season progress: `1.0`

## Top Table Rows

- 1. Barcelona P=38 Pts=94 PPM=2.4737 GF=95 GA=36 GD=59
- 2. Real Madrid P=38 Pts=86 PPM=2.2632 GF=77 GA=35 GD=42
- 3. Villarreal P=38 Pts=72 PPM=1.8947 GF=72 GA=46 GD=26
- 4. Atletico P=38 Pts=69 PPM=1.8158 GF=62 GA=44 GD=18
- 5. Real Betis P=38 Pts=60 PPM=1.5789 GF=59 GA=48 GD=11
- 6. Celta Vigo P=38 Pts=54 PPM=1.4211 GF=53 GA=48 GD=5
- 7. Getafe P=38 Pts=51 PPM=1.3421 GF=32 GA=38 GD=-6
- 8. Vallecano P=38 Pts=50 PPM=1.3158 GF=41 GA=44 GD=-3

## Feature Definitions

- `league_home_win_rate`: home result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_draw_rate`: draw result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_away_win_rate`: away result share normalized 0..1; Statshub may provide percent, otherwise count / matches_played
- `league_goals_per_match`: goals_total / matches_played when available; raw goal average, not normalized
- `league_btts_rate`: both teams to score total / matches_played, normalized 0..1
- `league_clean_sheet_rate`: clean sheet total / matches_played, normalized 0..1
- `league_over25_rate`: over 2.5 goals share from overunder['2.5']; Statshub observed value is percent, normalized 0..1
- `season_progress`: current_round / max_rounds, normalized 0..1
- `table_compactness_top5_ppm_gap`: points-per-match rank1 minus rank5; raw PPM gap
- `average_points_per_match`: mean table points_per_match across teams

## Client Metrics

```json
{
  "total_requests": 12,
  "success_count": 12,
  "retry_count": 0,
  "refresh_count": 0,
  "blocked_count": 0,
  "expired_count": 0,
  "empty_count": 0,
  "invalid_json_count": 0,
  "http_error_count": 0,
  "endpoint_timings_ms": {
    "stats_season_leaguesummary": [
      681.69
    ],
    "stats_season_teams2": [
      514.8
    ],
    "stats_season_fixtures2": [
      1181.91
    ],
    "stats_season_tables": [
      14656.64
    ],
    "stats_formtable": [
      436.05
    ],
    "stats_season_venues": [
      865.35
    ],
    "stats_season_injuries": [
      1210.81
    ],
    "stats_season_topgoals": [
      571.72
    ],
    "stats_season_topcards": [
      673.88
    ],
    "stats_season_topassists": [
      592.08
    ],
    "stats_season_teamscoringconceding": [
      690.05
    ],
    "stats_team_streaks": [
      486.79
    ]
  },
  "endpoint_timing_summary": {
    "stats_season_leaguesummary": {
      "count": 1,
      "min_ms": 681.69,
      "max_ms": 681.69,
      "avg_ms": 681.69
    },
    "stats_season_teams2": {
      "count": 1,
      "min_ms": 514.8,
      "max_ms": 514.8,
      "avg_ms": 514.8
    },
    "stats_season_fixtures2": {
      "count": 1,
      "min_ms": 1181.91,
      "max_ms": 1181.91,
      "avg_ms": 1181.91
    },
    "stats_season_tables": {
      "count": 1,
      "min_ms": 14656.64,
      "max_ms": 14656.64,
      "avg_ms": 14656.64
    },
    "stats_formtable": {
      "count": 1,
      "min_ms": 436.05,
      "max_ms": 436.05,
      "avg_ms": 436.05
    },
    "stats_season_venues": {
      "count": 1,
      "min_ms": 865.35,
      "max_ms": 865.35,
      "avg_ms": 865.35
    },
    "stats_season_injuries": {
      "count": 1,
      "min_ms": 1210.81,
      "max_ms": 1210.81,
      "avg_ms": 1210.81
    },
    "stats_season_topgoals": {
      "count": 1,
      "min_ms": 571.72,
      "max_ms": 571.72,
      "avg_ms": 571.72
    },
    "stats_season_topcards": {
      "count": 1,
      "min_ms": 673.88,
      "max_ms": 673.88,
      "avg_ms": 673.88
    },
    "stats_season_topassists": {
      "count": 1,
      "min_ms": 592.08,
      "max_ms": 592.08,
      "avg_ms": 592.08
    },
    "stats_season_teamscoringconceding": {
      "count": 1,
      "min_ms": 690.05,
      "max_ms": 690.05,
      "avg_ms": 690.05
    },
    "stats_team_streaks": {
      "count": 1,
      "min_ms": 486.79,
      "max_ms": 486.79,
      "avg_ms": 486.79
    }
  }
}
```

## Limitations

- Tournament to current season resolution is currently a small observed mapping, not a full resolver.
- Payloads are normalized compactly; raw responses are intentionally not embedded.
- Deep team scoring/streaks are sampled for the table leader only in this phase.
