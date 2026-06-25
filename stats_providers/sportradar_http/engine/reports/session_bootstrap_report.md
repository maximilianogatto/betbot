# Sportradar Session Bootstrap Report

- Generated at: `2026-06-19T05:01:26.702154+00:00`
- Runs: `2`

## Summary

### `headless`

- Usable for HTTP replay: `False`
- Token expiration UTC: `None`
- Token ACL: `None`
- Token data: `None`
- Document statuses: `{'https://statshub.sportradar.com/bet365/en/sport/1': 403, 'https://statshub.sportradar.com/bet365/en/match/61624678': 403}`
- Fetch/gismo responses: `0`
- Blocked payloads: `0`
- Expired payloads: `0`
- Endpoints seen: `[]`
- Error: `None`

### `headed`

- Usable for HTTP replay: `True`
- Token expiration UTC: `2026-06-20T06:17:04+00:00`
- Token ACL: `/*`
- Token data: `{'o': 'https://statshub.sportradar.com', 'a': 'bet365', 'act': 'origincheck', 'osrc': 'hostheader'}`
- Document statuses: `{'https://statshub.sportradar.com/bet365/en/sport/1': 200, 'https://statshub.sportradar.com/bet365/en/match/61624678': 200}`
- Fetch/gismo responses: `41`
- Blocked payloads: `0`
- Expired payloads: `0`
- Endpoints seen: `['odds_ukformat', 'event_get', 'unified_sport_matches_markets', 'sport_matches_prevnext', 'stats_sport_matches_prevnext', 'unified_sport_matches', 'config_tree_mini', 'stats_formtable', 'stats_season_tables', 'stats_team_nextx', 'stats_team_lastx', 'stats_team_versus', 'stats_season_injuries', 'match_info_statshub', 'stats_team_streaks', 'stats_match_get', 'stats_season_teamscoringconceding', 'match_timelinedelta', 'match_markets', 'stats_season_topassists', 'stats_season_topcards', 'stats_season_topgoals', 'match_details', 'stats_h2h_versus', 'match_timeline', 'uniqueteam_markets', 'match_info', 'stats_match_situation']`
- Error: `None`

## Operational Notes

- Browser bootstrap and HTTP replay are intentionally separate.
- `origin` and `referer` are mandatory replay headers based on prior probes.
- Headless may receive 403 at the document/bootstrap layer; headed is kept as fallback evidence.
- No token signing is attempted here. The manager only captures and reuses valid signed URLs.
