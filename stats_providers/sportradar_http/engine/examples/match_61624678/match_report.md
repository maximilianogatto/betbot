# Sportradar Match Pipeline Report

- Generated at: `2026-05-26T21:53:38.837909+00:00`
- Match: `Alaves vs Vallecano`
- Competition: `LaLiga 25/26`
- Kickoff UTC: `2026-05-23T19:00:00+00:00`
- Status: `Ended`
- Score: `1 - 2`

## Odds

- 1X2: `{}`
- Handicap markets: `0`
- Totals markets: `0`

## Match Stats

- `Ball possession`: home=47.0 away=53.0
- `Goal attempts`: home=9.0 away=11.0
- `Shots on target`: home=9.0 away=7.0
- `Shots off target`: home=0.0 away=4.0
- `Corner kicks`: home=10.0 away=5.0
- `Yellow cards`: home=3.0 away=3.0

## Features

- `form_gap`: `-4.0`
- `table_position_gap`: `-6.0`
- `attack_strength_home`: `1.421053`
- `attack_strength_away`: `1.105263`
- `btts_tendency_index`: `0.552632`
- `h2h_home_edge`: `-0.4`
- `live_pressure_home`: `0.5`
- `live_pressure_away`: `0.5`

## H2H

- Sample size: `10`
- `2026-05-23T19:00:00+00:00` Alaves 1-2 Vallecano
- `2026-01-14T20:00:00+00:00` Alaves 2-0 Vallecano
- `2025-10-26T20:00:00+00:00` Vallecano 1-0 Alaves
- `2025-03-29T17:30:00+00:00` Alaves 0-2 Vallecano
- `2024-10-26T14:15:00+00:00` Vallecano 1-0 Alaves

## Feature Definitions

- `form_gap`: home recent points minus away recent points over the normalized recent-match window; positive favors home
- `table_position_gap`: away table position minus home table position; positive means home is higher in the table
- `points_per_match_home`: home team table points / matches played; raw PPM
- `points_per_match_away`: away team table points / matches played; raw PPM
- `goals_for_avg_home_context`: home team's home-split goals scored average from team scoring payload
- `goals_for_avg_away_context`: away team's away-split goals scored average from team scoring payload
- `goals_against_avg_home_context`: home team's home-split goals conceded average from team scoring payload
- `goals_against_avg_away_context`: away team's away-split goals conceded average from team scoring payload
- `attack_strength_home`: mean(home home-split goals_for_avg, away away-split goals_against_avg); raw goals context, not probability
- `attack_strength_away`: mean(away away-split goals_for_avg, home home-split goals_against_avg); raw goals context, not probability
- `defense_weakness_home`: home team's home-split goals conceded average; higher means weaker defensive context
- `defense_weakness_away`: away team's away-split goals conceded average; higher means weaker defensive context
- `btts_tendency_index`: mean(home home-split BTTS rate, away away-split BTTS rate), normalized 0..1 when available
- `over_tendency_index`: mean attack environments for both sides: attack_strength_home and attack_strength_away; raw expected-goals context
- `h2h_sample_size`: number of normalized direct/versus H2H matches
- `h2h_home_edge`: (home_team_h2h_wins - away_team_h2h_wins) / h2h_sample_size, range -1..1
- `injuries_count_home`: count of normalized missing/doubtful injuries assigned to home team
- `injuries_count_away`: count of normalized missing/doubtful injuries assigned to away team
- `live_pressure_home`: home dangerous pressure share from match_situation, normalized 0..1
- `live_pressure_away`: away dangerous pressure share from match_situation, normalized 0..1
- `live_score_state`: categorical score state from live_state/final score

## Quality

```json
{
  "data_completeness": 1.0,
  "has_metadata": true,
  "has_odds_endpoint": true,
  "has_priced_odds": false,
  "has_table": true,
  "has_match_details": true,
  "has_team_form": true,
  "has_team_scoring": true,
  "has_h2h": true,
  "has_live_state": true,
  "missing_important_endpoints": []
}
```

## Client Metrics

```json
{
  "total_requests": 27,
  "success_count": 25,
  "retry_count": 0,
  "refresh_count": 1,
  "blocked_count": 2,
  "expired_count": 0,
  "empty_count": 0,
  "invalid_json_count": 0,
  "http_error_count": 0,
  "endpoint_timings_ms": {
    "match_info_statshub": [
      406.62
    ],
    "stats_match_get": [
      435.41
    ],
    "match_markets": [
      457.39
    ],
    "match_details": [
      852.94
    ],
    "stats_match_tableslice": [
      702.99
    ],
    "stats_match_head2head": [
      552.17
    ],
    "match_timeline": [
      695.24
    ],
    "match_timelinedelta": [
      715.2
    ],
    "stats_match_situation": [
      385.63
    ],
    "stats_team_lastx": [
      495.64,
      724.42
    ],
    "stats_team_nextx": [
      279.66,
      1149.33
    ],
    "stats_team_streaks": [
      783.97,
      674.86
    ],
    "stats_season_teamscoringconceding": [
      397.52,
      647.99
    ],
    "stats_season_topgoals": [
      590.62,
      750.28
    ],
    "stats_season_topcards": [
      564.06,
      659.67
    ],
    "stats_season_topassists": [
      692.13,
      709.48
    ],
    "stats_season_injuries": [
      792.29
    ],
    "stats_team_versus": [
      324.96
    ],
    "stats_h2h_versus": [
      581.02,
      558.75
    ]
  },
  "endpoint_timing_summary": {
    "match_info_statshub": {
      "count": 1,
      "min_ms": 406.62,
      "max_ms": 406.62,
      "avg_ms": 406.62
    },
    "stats_match_get": {
      "count": 1,
      "min_ms": 435.41,
      "max_ms": 435.41,
      "avg_ms": 435.41
    },
    "match_markets": {
      "count": 1,
      "min_ms": 457.39,
      "max_ms": 457.39,
      "avg_ms": 457.39
    },
    "match_details": {
      "count": 1,
      "min_ms": 852.94,
      "max_ms": 852.94,
      "avg_ms": 852.94
    },
    "stats_match_tableslice": {
      "count": 1,
      "min_ms": 702.99,
      "max_ms": 702.99,
      "avg_ms": 702.99
    },
    "stats_match_head2head": {
      "count": 1,
      "min_ms": 552.17,
      "max_ms": 552.17,
      "avg_ms": 552.17
    },
    "match_timeline": {
      "count": 1,
      "min_ms": 695.24,
      "max_ms": 695.24,
      "avg_ms": 695.24
    },
    "match_timelinedelta": {
      "count": 1,
      "min_ms": 715.2,
      "max_ms": 715.2,
      "avg_ms": 715.2
    },
    "stats_match_situation": {
      "count": 1,
      "min_ms": 385.63,
      "max_ms": 385.63,
      "avg_ms": 385.63
    },
    "stats_team_lastx": {
      "count": 2,
      "min_ms": 495.64,
      "max_ms": 724.42,
      "avg_ms": 610.03
    },
    "stats_team_nextx": {
      "count": 2,
      "min_ms": 279.66,
      "max_ms": 1149.33,
      "avg_ms": 714.5
    },
    "stats_team_streaks": {
      "count": 2,
      "min_ms": 674.86,
      "max_ms": 783.97,
      "avg_ms": 729.41
    },
    "stats_season_teamscoringconceding": {
      "count": 2,
      "min_ms": 397.52,
      "max_ms": 647.99,
      "avg_ms": 522.75
    },
    "stats_season_topgoals": {
      "count": 2,
      "min_ms": 590.62,
      "max_ms": 750.28,
      "avg_ms": 670.45
    },
    "stats_season_topcards": {
      "count": 2,
      "min_ms": 564.06,
      "max_ms": 659.67,
      "avg_ms": 611.87
    },
    "stats_season_topassists": {
      "count": 2,
      "min_ms": 692.13,
      "max_ms": 709.48,
      "avg_ms": 700.81
    },
    "stats_season_injuries": {
      "count": 1,
      "min_ms": 792.29,
      "max_ms": 792.29,
      "avg_ms": 792.29
    },
    "stats_team_versus": {
      "count": 1,
      "min_ms": 324.96,
      "max_ms": 324.96,
      "avg_ms": 324.96
    },
    "stats_h2h_versus": {
      "count": 2,
      "min_ms": 558.75,
      "max_ms": 581.02,
      "avg_ms": 569.88
    }
  }
}
```

## Limitations

- This is an offline research provider snapshot, not wired into BetBot production.
- Full raw payloads are not embedded; use raw_refs for traceability.
- match_markets can be empty for ended/unpriced matches.
