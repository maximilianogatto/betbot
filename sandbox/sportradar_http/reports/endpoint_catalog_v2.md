# Sportradar Endpoint Catalog v2

This catalog is generated from typed endpoint specs in `sandbox/sportradar_http/endpoints/catalog.py`.

| Endpoint | Path | Params | Namespace | Prematch | Live | Utility | Stability | Notes |
|---|---|---|---|---:|---:|---|---|---|
| `config_tree_mini` | `config_tree_mini/{category_id}/{depth}/{sport_id}` | `category_id, depth, sport_id` | `bet365/Etc:UTC` | `yes` | `no` | sport/category/league navigation tree | observed | Large payload. Useful for discovery bootstrap. |
| `event_get` | `event_get/` | `-` | `bet365/Etc:UTC` | `no` | `yes` | event/live polling feed | observed | - |
| `match_details` | `match_details/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `yes` | detailed match stats | observed | - |
| `match_info_statshub` | `match_info_statshub/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `yes` | match metadata: teams, season, kickoff | observed | - |
| `match_markets` | `match_markets/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `yes` | match odds/markets | observed | - |
| `match_timeline` | `match_timeline/{match_id}` | `match_id` | `bet365/Etc:UTC` | `no` | `yes` | full match timeline | observed | - |
| `match_timelinedelta` | `match_timelinedelta/{match_id}` | `match_id` | `bet365/Etc:UTC` | `no` | `yes` | timeline deltas/polling | observed | - |
| `odds_ukformat` | `odds_ukformat/` | `-` | `common/Etc:UTC` | `yes` | `yes` | odds format/config | observed | - |
| `season_markets` | `season_markets/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season market metadata | observed | - |
| `sport_matches_prevnext` | `sport_matches_prevnext/{sport_id}/{date}/{cursor}` | `sport_id, date, cursor` | `common/America:Montevideo` | `yes` | `no` | previous/next sport fixtures cursor | observed | - |
| `stats_formtable` | `stats_formtable/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | form table | observed | - |
| `stats_h2h_versus` | `stats_h2h_versus/{team_a_id}/{team_b_id}/{match_id}` | `team_a_id, team_b_id, match_id` | `bet365/Etc:UTC` | `yes` | `no` | direct H2H matches | observed | - |
| `stats_match_get` | `stats_match_get/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `yes` | match snapshot/status/stats | observed | - |
| `stats_match_head2head` | `stats_match_head2head/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `no` | match H2H context | observed | - |
| `stats_match_situation` | `stats_match_situation/{match_id}` | `match_id` | `common/Etc:UTC` | `no` | `yes` | live match situation | observed | - |
| `stats_match_tableslice` | `stats_match_tableslice/{match_id}` | `match_id` | `bet365/Etc:UTC` | `yes` | `no` | table slice around match teams | observed | - |
| `stats_season_fixtures2` | `stats_season_fixtures2/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season fixtures | observed | - |
| `stats_season_injuries` | `stats_season_injuries/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season injuries | observed | - |
| `stats_season_leaguesummary` | `stats_season_leaguesummary/{season_id}` | `season_id` | `common/Etc:UTC` | `yes` | `no` | league summary metadata | observed | - |
| `stats_season_meta` | `stats_season_meta/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season metadata | observed | - |
| `stats_season_tables` | `stats_season_tables/{season_id}/{table_id}/` | `season_id, table_id` | `bet365/Etc:UTC` | `yes` | `no` | standings/table | observed | Observed table_id can be empty string or 1. |
| `stats_season_teams2` | `stats_season_teams2/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season teams | observed | - |
| `stats_season_teamscoringconceding` | `stats_season_teamscoringconceding/{season_id}/{team_id}/{split_id}` | `season_id, team_id, split_id` | `common/Etc:UTC` | `yes` | `no` | goals scored/conceded distributions | observed | - |
| `stats_season_topassists` | `stats_season_topassists/{season_id}/{team_id}` | `season_id, team_id` | `bet365/Etc:UTC` | `yes` | `no` | top assists | observed | - |
| `stats_season_topcards` | `stats_season_topcards/{season_id}/{team_id}` | `season_id, team_id` | `bet365/Etc:UTC` | `yes` | `no` | top cards | observed | - |
| `stats_season_topgoals` | `stats_season_topgoals/{season_id}/{team_id}` | `season_id, team_id` | `bet365/Etc:UTC` | `yes` | `no` | top scorers | observed | - |
| `stats_season_venues` | `stats_season_venues/{season_id}` | `season_id` | `bet365/Etc:UTC` | `yes` | `no` | season venues | observed | - |
| `stats_sport_matches_prevnext` | `stats_sport_matches_prevnext/{sport_id}/{date}/{cursor}` | `sport_id, date, cursor` | `common/America:Montevideo` | `yes` | `no` | stats-aware previous/next sport fixtures cursor | observed | - |
| `stats_team_lastx` | `stats_team_lastx/{team_id}/{count}` | `team_id, count` | `bet365/Etc:UTC` | `yes` | `no` | recent team matches | observed | - |
| `stats_team_nextx` | `stats_team_nextx/{team_id}/{count}` | `team_id, count` | `bet365/Etc:UTC` | `yes` | `no` | upcoming team matches | observed | - |
| `stats_team_streaks` | `stats_team_streaks/{team_id}` | `team_id` | `common/Etc:UTC` | `yes` | `no` | team streaks/form signals | observed | - |
| `stats_team_versus` | `stats_team_versus/{team_a_id}/{team_b_id}/` | `team_a_id, team_b_id` | `bet365/Etc:UTC` | `yes` | `no` | team-vs-team context | observed | - |
| `unified_sport_matches` | `unified_sport_matches/{sport_id}/{date}/{cursor}` | `sport_id, date, cursor` | `bet365/America:Montevideo` | `yes` | `no` | sport-level fixtures by date | observed | Core discovery endpoint for fixtures. |
| `unified_sport_matches_markets` | `unified_sport_matches_markets/{sport_id}/{date}/{cursor}` | `sport_id, date, cursor` | `bet365/America:Montevideo` | `yes` | `no` | sport-level fixtures with market references | observed | Good candidate for odds-server discovery. |
| `uniqueteam_markets` | `uniqueteam_markets/{team_id}` | `team_id` | `bet365/Etc:UTC` | `yes` | `no` | team market metadata | observed | - |

## Replay Requirements

- Signed token `T=exp~acl~data~hmac` from browser bootstrap.
- `origin: https://statshub.sportradar.com`.
- `referer: https://statshub.sportradar.com/`.
- Browser must not stay open after bootstrap.
