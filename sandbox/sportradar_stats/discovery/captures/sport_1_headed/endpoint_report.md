# Sportradar / Statshub Discovery Endpoint Report

- Records: `43`
- Endpoints: `9`

## Role Coverage

- `match`: 26
- `sport`: 24
- `fixture`: 20
- `odds`: 12
- `league`: 7
- `navigation`: 7
- `team`: 6

## Endpoints

### `/bet365/en/sport/:id`

- Count: `4`
- Statuses: `{'200': 4}`
- Roles: `sport=4`
- Paths: `['/bet365/en/sport/:id']`
- Query URLs: `[]`
- ID patterns: `{'path_ids': ['1', '5', '2', '4'], 'query_ids': [], 'payload_ids': []}`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1`

### `config_tree_mini`

- Count: `6`
- Statuses: `{'200': 6}`
- Roles: `league=6, navigation=6`
- Paths: `['/config_tree_mini/:id/:id/:id']`
- Query URLs: `['config_tree_mini/67/0/1', 'config_tree_mini/67/0/5', 'config_tree_mini/67/0/2', 'config_tree_mini/67/0/4']`
- ID patterns: `{'path_ids': ['67', '0', '1', '5', '2', '4'], 'query_ids': [], 'payload_ids': ['1', '4', '55016', '2386', '105587', '2307', '2308', '2309', '2310', '53231', '6996', '2383', '105589', '147109', '147111', '147113', '3948', '101177', '3954', '3955']}`
- Top-level keys: `['_doc', '_id', '_sid', 'name', 'realcategories', '_sk']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/config_tree_mini/67/0/1?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `config_uniquetournamentsall`

- Count: `1`
- Statuses: `{'200': 1}`
- Roles: `league=1, navigation=1`
- Paths: `['/config_uniquetournamentsall/:id/:id/:id']`
- Query URLs: `['config_uniquetournamentsall/0/67/5']`
- ID patterns: `{'path_ids': ['0', '67', '5'], 'query_ids': [], 'payload_ids': ['14666', '14664', '2711', '2707', '2709', '31361', '31357', '31359', '41961', '41957', '41959', '48176', '48172', '48174', '2633', '2629', '2631', '2771', '2767', '2769']}`
- Top-level keys: `['_doc', '_id', '_utid', '_sid', '_rcid', 'name', 'currentseason', 'friendly', 'parent', '_sk', 'a2']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/config_uniquetournamentsall/0/67/5?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `event_get`

- Count: `6`
- Statuses: `{'200': 6}`
- Roles: `match=6, team=6`
- Paths: `['/event_get']`
- Query URLs: `['event_get/']`
- ID patterns: `{'path_ids': [], 'query_ids': [], 'payload_ids': ['2370418294', '71681250', '7', '34199836', '33993526', '2370418682', '71649874', '34029156', '34029152', '6', '2370419178', '71661600', '33313490', '25431263', '2370419414', '71698312', '10', '22957743', '26725055', '2370419612']}`
- Top-level keys: `['_doc', '_doctype', '_id', '_scoutid', '_sid', '_rcid', '_tid', '_dc', '_typeid', 'uts', 'updated_uts', 'type', 'matchid', 'disabled', 'time', 'seconds', 'injurytime', 'team', 'name', 'updatedate']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/Etc:UTC/gismo/event_get/?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `odds_ukformat`

- Count: `6`
- Statuses: `{'200': 6}`
- Roles: `odds=6`
- Paths: `['/odds_ukformat']`
- Query URLs: `['odds_ukformat/']`
- ID patterns: `{'path_ids': [], 'query_ids': [], 'payload_ids': []}`
- Top-level keys: `['dec', 'frac']`
- Example URL: `https://sh.fn.sportradar.com/common/en/Etc:UTC/gismo/odds_ukformat/?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `sport_matches_prevnext`

- Count: `4`
- Statuses: `{'200': 4}`
- Roles: `fixture=4, match=4, sport=4`
- Paths: `['/sport_matches_prevnext/:id/2026-05-25/:id']`
- Query URLs: `['sport_matches_prevnext/1/2026-05-25/0', 'sport_matches_prevnext/5/2026-05-25/0', 'sport_matches_prevnext/2/2026-05-25/0', 'sport_matches_prevnext/4/2026-05-25/0']`
- ID patterns: `{'path_ids': ['1', '0', '5', '2', '4'], 'query_ids': [], 'payload_ids': ['66299228', '843', '841', '855', '853', '845', '847', '5519', '6413', '100', '71658354', '20191285', '153', '15482275', '71670764', '28', '1151', '1149', '1155', '1157']}`
- Top-level keys: `['previous', 'next', 'validCalendarDates']`
- Example URL: `https://sh.fn.sportradar.com/common/en/America:Montevideo/gismo/sport_matches_prevnext/1/2026-05-25/0?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `stats_sport_matches_prevnext`

- Count: `4`
- Statuses: `{'200': 4}`
- Roles: `fixture=4, match=4, sport=4`
- Paths: `['/stats_sport_matches_prevnext/:id/2026-05-25/:id']`
- Query URLs: `['stats_sport_matches_prevnext/1/2026-05-25/0', 'stats_sport_matches_prevnext/5/2026-05-25/0', 'stats_sport_matches_prevnext/2/2026-05-25/0', 'stats_sport_matches_prevnext/4/2026-05-25/0']`
- ID patterns: `{'path_ids': ['1', '0', '5', '2', '4'], 'query_ids': [], 'payload_ids': ['68746862', '12553590', '9609970', '1', '71670764', '9838964', '226', '30802923', '28', '8', '71659354', '8823095', '13', '24062873', '69748626', '11167457', '11166799', '122', '71655922', '34142252']}`
- Top-level keys: `['previous', 'next', 'validCalendarDates']`
- Example URL: `https://sh.fn.sportradar.com/common/en/America:Montevideo/gismo/stats_sport_matches_prevnext/1/2026-05-25/0?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `unified_sport_matches`

- Count: `6`
- Statuses: `{'200': 6}`
- Roles: `fixture=6, match=6, sport=6`
- Paths: `['/unified_sport_matches/:id/2026-05-25/:id']`
- Query URLs: `['unified_sport_matches/1/2026-05-25/0', 'unified_sport_matches/5/2026-05-25/0', 'unified_sport_matches/2/2026-05-25/0', 'unified_sport_matches/4/2026-05-25/0']`
- ID patterns: `{'path_ids': ['1', '0', '5', '2', '4'], 'query_ids': [], 'payload_ids': ['1', '304', '3', '3657', '133306', '48', '10', '10427', '138214', '85968', '140338', '127687', '146255', '140046', '296', '11', '9174', '132744', '34', '13']}`
- Top-level keys: `['sport']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/America:Montevideo/gismo/unified_sport_matches/1/2026-05-25/0?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

### `unified_sport_matches_markets`

- Count: `6`
- Statuses: `{'200': 6}`
- Roles: `fixture=6, match=6, odds=6, sport=6`
- Paths: `['/unified_sport_matches_markets/:id/2026-05-25/:id']`
- Query URLs: `['unified_sport_matches_markets/1/2026-05-25/0', 'unified_sport_matches_markets/5/2026-05-25/0', 'unified_sport_matches_markets/2/2026-05-25/0', 'unified_sport_matches_markets/4/2026-05-25/0']`
- ID patterns: `{'path_ids': ['1', '0', '5', '2', '4'], 'query_ids': [], 'payload_ids': []}`
- Top-level keys: `['matches']`
- Example URL: `https://sh.fn.sportradar.com/bet365/en/America:Montevideo/gismo/unified_sport_matches_markets/1/2026-05-25/0?T=exp=1779767584~acl=/*~data=eyJvIjoiaHR0cHM6Ly9zdGF0c2h1Yi5zcG9ydHJhZGFyLmNvbSIsImEiOiJiZXQzNjUiLCJhY3QiOiJvcmlnaW5jaGVjayIsIm9zcmMiOiJob3N0aGVhZGVyIn0~hmac=19e340b4c8562fcb51836635e10a6a846f1cead08c797511c1b32f81f57454d2`

## Initial Conclusions

- Endpoints with `sport`, `league`, `fixture`, `schedule`, or `standings` roles are candidates for browserless discovery.
- Repeated signed URLs with `T=exp=...` should be treated as reusable only within their signature window until HTTP probing confirms otherwise.
- This report intentionally maps API shape only; it does not normalize full fixtures or integrate with BetBot.
