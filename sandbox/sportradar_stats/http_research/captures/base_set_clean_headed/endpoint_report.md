# Statshub/Sportradar Endpoint Catalog

- Records: `74`
- Endpoints: `43`

## Classification Coverage

- `historical`: 35
- `stats`: 31
- `league`: 26
- `match`: 21
- `sport`: 12
- `fixtures`: 12
- `odds`: 11
- `team`: 11
- `discovery`: 9
- `live_state`: 9
- `players`: 9
- `prematch`: 7
- `standings`: 7
- `form`: 6
- `timeline`: 4
- `config`: 4
- `h2h`: 2
- `injuries`: 1

## Endpoints

### `/bet365/en/match/:id`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/match/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/match/61624678`

### `/bet365/en/sport/:id`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1`

### `/bet365/en/sport/:id/tournament/:id`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `league=1, sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id/tournament/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1/tournament/8`

### `/bet365/en/sport/:id/tournament/:id/fixtures`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `fixtures=1, league=1, sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id/tournament/:id/fixtures']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1/tournament/8/fixtures?view=round`

### `config_tree_mini`

- Count: `3`
- Statuses: `{'200': 3}`
- Classification: `discovery=3, league=3, sport=3`
- Signed token: `True`
- Query URLs: `['config_tree_mini/67/0/1', 'config_tree_mini/67/0/1/32']`
- Normalized paths: `['/config_tree_mini/:id/:id/:id', '/config_tree_mini/:id/:id/:id/:id']`
- Top-level keys: `['_doc', '_id', '_sid', 'name', 'realcategories', '_sk']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/config_tree_mini/67/0/1?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `event_get`

- Count: `4`
- Statuses: `{'200': 4}`
- Classification: `live_state=4, match=4`
- Signed token: `True`
- Query URLs: `['event_get/']`
- Normalized paths: `['/event_get']`
- Top-level keys: `['_doc', '_doctype', '_id', '_scoutid', '_sid', '_rcid', '_tid', '_dc', '_typeid', 'uts', 'updated_uts', 'type', 'matchid', 'disabled', 'time', 'seconds', 'injurytime', 'team', 'name', 'updatedate', 'period', 'status', 'match']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/event_get/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `livescore_season_fixtures`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `fixtures=1, historical=1`
- Signed token: `True`
- Query URLs: `['livescore_season_fixtures/130805']`
- Normalized paths: `['/livescore_season_fixtures/:id']`
- Top-level keys: `['matches', 'tournaments', 'uniquetournaments', 'categories', 'sports', 'venues']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/livescore_season_fixtures/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `match_details`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1, prematch=1, stats=1`
- Signed token: `True`
- Query URLs: `['match_details/61624678']`
- Normalized paths: `['/match_details/:id']`
- Top-level keys: `['_doc', '_matchid', 'teams', 'index', 'values', 'types']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_details/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `match_info`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1`
- Signed token: `True`
- Query URLs: `['match_info/61624678']`
- Normalized paths: `['/match_info/:id']`
- Top-level keys: `['_doc', 'match', 'cities', 'stadium', 'tournament', 'uniquetournament', 'sport', 'realcategory', 'season', 'referee', 'attendance', 'manager', 'jerseys', 'statscoverage']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/match_info/61624678?T=exp=1779849147~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJzdGF0c2h1YiIsImFjdCI6Im9yaWdpbmNoZWNrIiwib3NyYyI6Im9yaWdpbiJ9~hmac=669d5a5b34722820beb55b239968aad52d9bf17a3f773e82b19686a6d83202eb`

### `match_info_statshub`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1, prematch=1, stats=1`
- Signed token: `True`
- Query URLs: `['match_info_statshub/61624678']`
- Normalized paths: `['/match_info_statshub/:id']`
- Top-level keys: `['_doc', 'match', 'cities', 'stadium', 'tournament', 'uniquetournament', 'sport', 'realcategory', 'season', 'referee', 'attendance', 'manager', 'jerseys', 'statscoverage']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_info_statshub/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `match_markets`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1, odds=1`
- Signed token: `True`
- Query URLs: `['match_markets/61624678']`
- Normalized paths: `['/match_markets/:id']`
- Top-level keys: `['markets']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_markets/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `match_timeline`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `live_state=2, match=2, timeline=2`
- Signed token: `True`
- Query URLs: `['match_timeline/61624678']`
- Normalized paths: `['/match_timeline/:id']`
- Top-level keys: `['match', 'events']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timeline/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `match_timelinedelta`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `live_state=2, match=2, timeline=2`
- Signed token: `True`
- Query URLs: `['match_timelinedelta/61624678']`
- Normalized paths: `['/match_timelinedelta/:id']`
- Top-level keys: `['match', 'events']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/match_timelinedelta/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `odds_ukformat`

- Count: `4`
- Statuses: `{'200': 4}`
- Classification: `config=4, odds=4`
- Signed token: `True`
- Query URLs: `['odds_ukformat/']`
- Normalized paths: `['/odds_ukformat']`
- Top-level keys: `['dec', 'frac']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/odds_ukformat/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `season_markets`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `historical=2, odds=2`
- Signed token: `True`
- Query URLs: `['season_markets/130805']`
- Normalized paths: `['/season_markets/:id']`
- Top-level keys: `['matches']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/season_markets/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `sport_matches_prevnext`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `discovery=1, fixtures=1, match=1, sport=1`
- Signed token: `True`
- Query URLs: `['sport_matches_prevnext/1/2026-05-26/0']`
- Normalized paths: `['/sport_matches_prevnext/:id/:date/:id']`
- Top-level keys: `['previous', 'next', 'validCalendarDates']`
- Example URL: `https://sh.fn.sportradar.com/common/en/America:Montevideo/gismo/sport_matches_prevnext/1/2026-05-26/0?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_formtable`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `form=2, historical=2, league=2, standings=2, stats=2`
- Signed token: `True`
- Query URLs: `['stats_formtable/130805']`
- Normalized paths: `['/stats_formtable/:id']`
- Top-level keys: `['matchtype', 'tabletype', 'season', 'winpoints', 'losspoints', 'currentround', 'teams']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_formtable/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_h2h_versus`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `h2h=1, stats=1`
- Signed token: `True`
- Query URLs: `['stats_h2h_versus/2818/2885/61624678']`
- Normalized paths: `['/stats_h2h_versus/:id/:id/:id']`
- Top-level keys: `['match', 'lastmatchesbetweenteams', 'lastmatchesbetweenteamsonvenue', 'versusmatchstats']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_h2h_versus/2818/2885/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_match_get`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `live_state=1, match=1, prematch=1, stats=1`
- Signed token: `True`
- Query URLs: `['stats_match_get/61624678']`
- Normalized paths: `['/stats_match_get/:id']`
- Top-level keys: `['_doc', '_doctype', '_id', '_sid', '_rcid', '_tid', '_utid', 'round', 'week', 'teams', 'tobeannounced', 'postponed', 'stadiumid', 'walkover', 'retired', 'comment', 'inlivescore', 'disqualified', 'neutralground', 'canceled', 'bestof', 'periods', 'result', 'status', 'time']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_match_get/61624678?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_match_situation`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `match=1`
- Signed token: `True`
- Query URLs: `['stats_match_situation/61624678']`
- Normalized paths: `['/stats_match_situation/:id']`
- Top-level keys: `['_doc', 'matchid', 'data']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/stats_match_situation/61624678?T=exp=1779849147~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJzdGF0c2h1YiIsImFjdCI6Im9yaWdpbmNoZWNrIiwib3NyYyI6Im9yaWdpbiJ9~hmac=669d5a5b34722820beb55b239968aad52d9bf17a3f773e82b19686a6d83202eb`

### `stats_season_fixtures2`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `fixtures=2, historical=2`
- Signed token: `True`
- Query URLs: `['stats_season_fixtures2/130805']`
- Normalized paths: `['/stats_season_fixtures2/:id']`
- Top-level keys: `['_id', '_doc', '_utid', '_sid', 'name', 'abbr', 'start', 'end', 'neutralground', 'friendly', 'currentseasonid', 'year', 'matches', 'cups', 'tables', 'tournaments']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_fixtures2/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_injuries`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1, injuries=1, league=1, stats=1`
- Signed token: `True`
- Query URLs: `['stats_season_injuries/130805']`
- Normalized paths: `['/stats_season_injuries/:id']`
- Top-level keys: `['_doc', '_id', '_tid', '_playerid', 'status', 'player', 'uniqueteam']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_injuries/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_lastx`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1`
- Signed token: `True`
- Query URLs: `['stats_season_lastx/130805/20']`
- Normalized paths: `['/stats_season_lastx/:id/:id']`
- Top-level keys: `['season', 'matches', 'tournaments']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_lastx/130805/20?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_leaguesummary`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1, league=1`
- Signed token: `True`
- Query URLs: `['stats_season_leaguesummary/130805']`
- Normalized paths: `['/stats_season_leaguesummary/:id']`
- Top-level keys: `['_doc', 'matches', 'goals', 'overunder', 'clean_sheet', 'both_teams_to_score', 'cards', 'goalsbyperiod', 'pr_match_stats']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/stats_season_leaguesummary/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_meta`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1`
- Signed token: `True`
- Query URLs: `['stats_season_meta/130805']`
- Normalized paths: `['/stats_season_meta/:id']`
- Top-level keys: `['season', 'sport', 'realcategory', 'tournamentids', 'tableids', 'cupids', 'uniquetournament', 'statscoverage']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_meta/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_nextx`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1`
- Signed token: `True`
- Query URLs: `['stats_season_nextx/130805/20']`
- Normalized paths: `['/stats_season_nextx/:id/:id']`
- Top-level keys: `['season']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_nextx/130805/20?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_tables`

- Count: `5`
- Statuses: `{'200': 5}`
- Classification: `historical=5, league=5, standings=5, stats=5`
- Signed token: `True`
- Query URLs: `['stats_season_tables/130805', 'stats_season_tables/130805/1']`
- Normalized paths: `['/stats_season_tables/:id', '/stats_season_tables/:id/:id']`
- Top-level keys: `['_id', '_doc', '_utid', '_sid', 'name', 'abbr', 'start', 'end', 'neutralground', 'friendly', 'currentseasonid', 'year', 'tables']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_tables/130805//?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_teams2`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `historical=2`
- Signed token: `True`
- Query URLs: `['stats_season_teams2/130805']`
- Normalized paths: `['/stats_season_teams2/:id']`
- Top-level keys: `['season', 'teams', 'tables']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_teams2/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_teamscoringconceding`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `historical=2, league=2, stats=2, team=2`
- Signed token: `True`
- Query URLs: `['stats_season_teamscoringconceding/130805/2885/-1', 'stats_season_teamscoringconceding/130805/2818/-1']`
- Normalized paths: `['/stats_season_teamscoringconceding/:id/:id/-1']`
- Top-level keys: `['team', 'stats']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/stats_season_teamscoringconceding/130805/2885/-1?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_topassists`

- Count: `3`
- Statuses: `{'200': 3}`
- Classification: `historical=3, league=3, players=3, stats=3`
- Signed token: `True`
- Query URLs: `['stats_season_topassists/130805', 'stats_season_topassists/130805/2885', 'stats_season_topassists/130805/2818']`
- Normalized paths: `['/stats_season_topassists/:id', '/stats_season_topassists/:id/:id']`
- Top-level keys: `['season', 'players', 'teams']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_topassists/130805/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_topcards`

- Count: `3`
- Statuses: `{'200': 3}`
- Classification: `historical=3, league=3, players=3, stats=3`
- Signed token: `True`
- Query URLs: `['stats_season_topcards/130805', 'stats_season_topcards/130805/2818', 'stats_season_topcards/130805/2885']`
- Normalized paths: `['/stats_season_topcards/:id', '/stats_season_topcards/:id/:id']`
- Top-level keys: `['season', 'players', 'teams']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_topcards/130805/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_topgoals`

- Count: `3`
- Statuses: `{'200': 3}`
- Classification: `historical=3, league=3, players=3, stats=3`
- Signed token: `True`
- Query URLs: `['stats_season_topgoals/130805', 'stats_season_topgoals/130805/2885', 'stats_season_topgoals/130805/2818']`
- Normalized paths: `['/stats_season_topgoals/:id', '/stats_season_topgoals/:id/:id']`
- Top-level keys: `['season', 'players', 'teams']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_topgoals/130805/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_uniqueteamstats`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1`
- Signed token: `True`
- Query URLs: `['stats_season_uniqueteamstats/130805']`
- Normalized paths: `['/stats_season_uniqueteamstats/:id']`
- Top-level keys: `['season', 'stats']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_uniqueteamstats/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_season_venues`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1`
- Signed token: `True`
- Query URLs: `['stats_season_venues/130805']`
- Normalized paths: `['/stats_season_venues/:id']`
- Top-level keys: `['season', 'stadiums']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_season_venues/130805?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_sport_matches_prevnext`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `discovery=1, fixtures=1, match=1, sport=1, stats=1`
- Signed token: `True`
- Query URLs: `['stats_sport_matches_prevnext/1/2026-05-26/0']`
- Normalized paths: `['/stats_sport_matches_prevnext/:id/:date/:id']`
- Top-level keys: `['previous', 'next', 'validCalendarDates']`
- Example URL: `https://sh.fn.sportradar.com/common/en/America:Montevideo/gismo/stats_sport_matches_prevnext/1/2026-05-26/0?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_team_lastx`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `form=2, stats=2, team=2`
- Signed token: `True`
- Query URLs: `['stats_team_lastx/2885/20', 'stats_team_lastx/2818/20']`
- Normalized paths: `['/stats_team_lastx/:id/:id']`
- Top-level keys: `['team', 'matches', 'tournaments', 'uniquetournaments', 'realcategories']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_team_lastx/2885/20?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_team_nextx`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `fixtures=2, stats=2, team=2`
- Signed token: `True`
- Query URLs: `['stats_team_nextx/2885/1', 'stats_team_nextx/2818/1']`
- Normalized paths: `['/stats_team_nextx/:id/:id']`
- Top-level keys: `['team', 'matches', 'tournaments', 'uniquetournaments', 'realcategories']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_team_nextx/2885/1?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_team_streaks`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `form=2, historical=2, stats=2, team=2`
- Signed token: `True`
- Query URLs: `['stats_team_streaks/2885', 'stats_team_streaks/2818']`
- Normalized paths: `['/stats_team_streaks/:id']`
- Top-level keys: `['team', 'lastmatchesform', 'streaks', 'nextmatches']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/stats_team_streaks/2885?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `stats_team_versus`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `h2h=1, stats=1, team=1`
- Signed token: `True`
- Query URLs: `['stats_team_versus/2885/2818']`
- Normalized paths: `['/stats_team_versus/:id/:id']`
- Top-level keys: `['livematchid', 'matches', 'tournaments', 'realcategories', 'teams', 'currentmanagers', 'jersey', 'next']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/stats_team_versus/2885/2818/?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `unified_sport_matches`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `discovery=2, fixtures=2, match=2, prematch=2, sport=2`
- Signed token: `True`
- Query URLs: `['unified_sport_matches/1/2026-05-26/0']`
- Normalized paths: `['/unified_sport_matches/:id/:date/:id']`
- Top-level keys: `['sport']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/America:Montevideo/gismo/unified_sport_matches/1/2026-05-26/0?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `unified_sport_matches_markets`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `discovery=2, fixtures=2, match=2, odds=2, prematch=2, sport=2`
- Signed token: `True`
- Query URLs: `['unified_sport_matches_markets/1/2026-05-26/0']`
- Normalized paths: `['/unified_sport_matches_markets/:id/:date/:id']`
- Top-level keys: `['matches']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/America:Montevideo/gismo/unified_sport_matches_markets/1/2026-05-26/0?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `uniqueteam_markets`

- Count: `2`
- Statuses: `{'200': 2}`
- Classification: `odds=2, team=2`
- Signed token: `True`
- Query URLs: `['uniqueteam_markets/2885', 'uniqueteam_markets/2818']`
- Normalized paths: `['/uniqueteam_markets/:id']`
- Top-level keys: `['matches']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/uniqueteam_markets/2885?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

### `uniquetournament_seasonswinners`

- Count: `1`
- Statuses: `{'200': 1}`
- Classification: `historical=1, league=1`
- Signed token: `True`
- Query URLs: `['uniquetournament_seasonswinners/8']`
- Normalized paths: `['/uniquetournament_seasonswinners/:id']`
- Top-level keys: `['seasons']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/uniquetournament_seasonswinners/8?T=exp=1779853984~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=6abe6b83b324bf267e0e55357d286d679059119e534e19db1f2b34b70fa2907e`

