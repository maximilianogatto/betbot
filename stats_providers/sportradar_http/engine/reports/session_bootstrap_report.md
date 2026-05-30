# Sportradar Session Bootstrap Report

- Generated at: `2026-05-26T04:51:13.967041+00:00`
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
- Token expiration UTC: `2026-05-27T06:17:04+00:00`
- Token ACL: `/*`
- Token data: `{'o': 'https://statshub.sportradar.com', 'a': 'bet365', 'act': 'origincheck', 'osrc': 'hostheader'}`
- Document statuses: `{'https://statshub.sportradar.com/bet365/en/sport/1': 200, 'https://statshub.sportradar.com/bet365/en/match/61624678': 200}`
- Fetch/gismo responses: `41`
- Blocked payloads: `0`
- Expired payloads: `0`
- Endpoints seen: `['unified_sport_matches', 'odds_ukformat', 'unified_sport_matches_markets', 'config_tree_mini', 'sport_matches_prevnext', 'stats_sport_matches_prevnext', 'event_get', 'match_info_statshub', 'stats_match_get', 'stats_team_nextx', 'stats_formtable', 'stats_team_lastx', 'stats_team_versus', 'stats_season_topgoals', 'stats_season_topcards', 'stats_season_tables', 'stats_season_topassists', 'stats_season_teamscoringconceding', 'stats_team_streaks', 'stats_h2h_versus', 'stats_season_injuries', 'match_markets', 'uniqueteam_markets', 'match_timelinedelta', 'match_details', 'match_timeline', 'match_info', 'stats_match_situation']`
- Error: `None`

## Operational Notes

- Browser bootstrap and HTTP replay are intentionally separate.
- `origin` and `referer` are mandatory replay headers based on prior probes.
- Headless may receive 403 at the document/bootstrap layer; headed is kept as fallback evidence.
- No token signing is attempted here. The manager only captures and reuses valid signed URLs.
