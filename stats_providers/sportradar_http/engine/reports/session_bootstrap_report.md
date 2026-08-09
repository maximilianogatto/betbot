# Sportradar Session Bootstrap Report

- Generated at: `2026-06-27T17:09:55.427316+00:00`
- Runs: `1`

## Summary

### `headed`

- Usable for HTTP replay: `True`
- Token expiration UTC: `2026-06-28T18:17:04+00:00`
- Token ACL: `/*`
- Token data: `{'o': 'https://statshub.sportradar.com', 'a': 'bet365', 'act': 'origincheck', 'osrc': 'hostheader'}`
- Document statuses: `{'https://statshub.sportradar.com/bet365/en/sport/1': 200, 'https://statshub.sportradar.com/bet365/en/match/61624678': 200}`
- Fetch/gismo responses: `43`
- Blocked payloads: `0`
- Expired payloads: `0`
- Endpoints seen: `['config_tree_mini', 'sport_matches_prevnext', 'unified_sport_matches_markets', 'odds_ukformat', 'stats_sport_matches_prevnext', 'event_get', 'unified_sport_matches', 'stats_team_lastx', 'match_info_statshub', 'stats_match_get', 'stats_match_head2head', 'stats_team_nextx', 'stats_season_tables', 'stats_formtable', 'stats_team_versus', 'stats_season_topgoals', 'stats_season_topcards', 'stats_season_topassists', 'stats_season_teamscoringconceding', 'stats_team_streaks', 'stats_season_injuries', 'match_markets', 'stats_match_tableslice', 'stats_h2h_versus', 'uniqueteam_markets', 'match_timelinedelta', 'match_timeline', 'match_details', 'match_info', 'stats_match_situation']`
- Error: `None`

## Operational Notes

- Browser bootstrap and HTTP replay are intentionally separate.
- `origin` and `referer` are mandatory replay headers based on prior probes.
- Headless may receive 403 at the document/bootstrap layer; headed is kept as fallback evidence.
- No token signing is attempted here. The manager only captures and reuses valid signed URLs.
