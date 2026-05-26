# Statshub Signed Token Analysis

- Generated at: `2026-05-26T03:40:11.719712+00:00`
- Source: `sandbox/sportradar_stats/http_research/captures/base_set_clean_headed/fetch_only.ndjson`
- Signed URLs: `20`

## Token Payloads

### exp `1779853984`

- Expires UTC: `2026-05-27T03:53:04+00:00`
- ACL: `/*`
- Data: `{'o': 'https://statshub.sportradar.com', 'a': 'bet365', 'act': 'origincheck', 'osrc': 'hostheader'}`
- Endpoints: `['sport_matches_prevnext', 'config_tree_mini', 'unified_sport_matches', 'stats_sport_matches_prevnext', 'odds_ukformat', 'unified_sport_matches_markets', 'event_get', 'stats_season_tables', 'stats_season_teams2', 'stats_formtable', 'stats_season_leaguesummary', 'stats_season_uniqueteamstats', 'stats_season_lastx', 'stats_season_nextx', 'stats_season_venues', 'uniquetournament_seasonswinners', 'stats_season_fixtures2', 'stats_season_topassists', 'stats_season_topgoals', 'stats_season_topcards']`


## Replay Mutations

- `unified_sport_matches` -> `unified_sport_matches_markets` status=200 outcome=reusable
- `unified_sport_matches_markets` -> `unified_sport_matches` status=200 outcome=reusable
