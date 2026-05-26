# Sportradar Match Pipeline Report

- Generated at: `2026-05-26T21:25:10.276148+00:00`
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
      343.84
    ],
    "stats_match_get": [
      328.88
    ],
    "match_markets": [
      364.63
    ],
    "match_details": [
      379.22
    ],
    "stats_match_tableslice": [
      767.6
    ],
    "stats_match_head2head": [
      704.49
    ],
    "match_timeline": [
      363.08
    ],
    "match_timelinedelta": [
      324.49
    ],
    "stats_match_situation": [
      383.52
    ],
    "stats_team_lastx": [
      885.92,
      894.53
    ],
    "stats_team_nextx": [
      758.25,
      736.1
    ],
    "stats_team_streaks": [
      316.3,
      317.2
    ],
    "stats_season_teamscoringconceding": [
      348.92,
      470.13
    ],
    "stats_season_topgoals": [
      326.86,
      298.4
    ],
    "stats_season_topcards": [
      580.53,
      295.47
    ],
    "stats_season_topassists": [
      1068.16,
      303.52
    ],
    "stats_season_injuries": [
      431.3
    ],
    "stats_team_versus": [
      648.7
    ],
    "stats_h2h_versus": [
      747.62,
      568.23
    ]
  },
  "endpoint_timing_summary": {
    "match_info_statshub": {
      "count": 1,
      "min_ms": 343.84,
      "max_ms": 343.84,
      "avg_ms": 343.84
    },
    "stats_match_get": {
      "count": 1,
      "min_ms": 328.88,
      "max_ms": 328.88,
      "avg_ms": 328.88
    },
    "match_markets": {
      "count": 1,
      "min_ms": 364.63,
      "max_ms": 364.63,
      "avg_ms": 364.63
    },
    "match_details": {
      "count": 1,
      "min_ms": 379.22,
      "max_ms": 379.22,
      "avg_ms": 379.22
    },
    "stats_match_tableslice": {
      "count": 1,
      "min_ms": 767.6,
      "max_ms": 767.6,
      "avg_ms": 767.6
    },
    "stats_match_head2head": {
      "count": 1,
      "min_ms": 704.49,
      "max_ms": 704.49,
      "avg_ms": 704.49
    },
    "match_timeline": {
      "count": 1,
      "min_ms": 363.08,
      "max_ms": 363.08,
      "avg_ms": 363.08
    },
    "match_timelinedelta": {
      "count": 1,
      "min_ms": 324.49,
      "max_ms": 324.49,
      "avg_ms": 324.49
    },
    "stats_match_situation": {
      "count": 1,
      "min_ms": 383.52,
      "max_ms": 383.52,
      "avg_ms": 383.52
    },
    "stats_team_lastx": {
      "count": 2,
      "min_ms": 885.92,
      "max_ms": 894.53,
      "avg_ms": 890.22
    },
    "stats_team_nextx": {
      "count": 2,
      "min_ms": 736.1,
      "max_ms": 758.25,
      "avg_ms": 747.17
    },
    "stats_team_streaks": {
      "count": 2,
      "min_ms": 316.3,
      "max_ms": 317.2,
      "avg_ms": 316.75
    },
    "stats_season_teamscoringconceding": {
      "count": 2,
      "min_ms": 348.92,
      "max_ms": 470.13,
      "avg_ms": 409.52
    },
    "stats_season_topgoals": {
      "count": 2,
      "min_ms": 298.4,
      "max_ms": 326.86,
      "avg_ms": 312.63
    },
    "stats_season_topcards": {
      "count": 2,
      "min_ms": 295.47,
      "max_ms": 580.53,
      "avg_ms": 438.0
    },
    "stats_season_topassists": {
      "count": 2,
      "min_ms": 303.52,
      "max_ms": 1068.16,
      "avg_ms": 685.84
    },
    "stats_season_injuries": {
      "count": 1,
      "min_ms": 431.3,
      "max_ms": 431.3,
      "avg_ms": 431.3
    },
    "stats_team_versus": {
      "count": 1,
      "min_ms": 648.7,
      "max_ms": 648.7,
      "avg_ms": 648.7
    },
    "stats_h2h_versus": {
      "count": 2,
      "min_ms": 568.23,
      "max_ms": 747.62,
      "avg_ms": 657.92
    }
  }
}
```

## Limitations

- This is an offline research provider snapshot, not wired into BetBot production.
- Full raw payloads are not embedded; use raw_refs for traceability.
- match_markets can be empty for ended/unpriced matches.
