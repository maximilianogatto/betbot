# Statshub/Sportradar API Feasibility

## Evidence Summary

- Catalog endpoints: `43`
- Signed gismo endpoints: `39`
- Direct document endpoints observed: `['/bet365/en/match/:id', '/bet365/en/sport/:id', '/bet365/en/sport/:id/tournament/:id', '/bet365/en/sport/:id/tournament/:id/fixtures']`
- Replay reusable attempts: `60`
- Replay blocked attempts: `40`
- Replay expired attempts: `0`
- Reusable endpoints sampled: `['sport_matches_prevnext', 'config_tree_mini', 'unified_sport_matches', 'stats_sport_matches_prevnext', 'odds_ukformat', 'unified_sport_matches_markets', 'event_get', 'stats_season_tables', 'stats_season_teams2', 'stats_formtable', 'stats_season_leaguesummary', 'stats_season_uniqueteamstats', 'stats_season_lastx', 'stats_season_nextx', 'stats_season_venues', 'uniquetournament_seasonswinners', 'stats_season_fixtures2', 'stats_season_topassists', 'stats_season_topgoals', 'stats_season_topcards']`
- Attempts blocked without origin/referer: `40`
- Attempts reusable with minimal origin/referer: `20`
- Attempts reusable with captured headers: `40`
- Token samples: `["exp=1779853984 expires=2026-05-27T03:53:04+00:00 acl=/* data={'o': 'https://statshub.sportradar.com', 'a': 'bet365', 'act': 'origincheck', 'osrc': 'hostheader'}"]`

## HTTP Replay Findings

- Direct document URLs are useful as browser bootstrap pages, not as the main data API.
- Useful data lives behind `/gismo/<endpoint>/...` URLs signed with `T=exp~acl~data~hmac`.
- The captured token data points to an origin check for `https://statshub.sportradar.com` and app `bet365`.
- Replays without `origin`/`referer` returned a small JSON exception body while still using HTTP 200.
- Replays with `origin: https://statshub.sportradar.com` and `referer: https://statshub.sportradar.com/` returned full JSON payloads.
- Token mutation tests show the same broad `acl=/*` token can be reused across at least some sibling endpoints while it is valid.
- A headless browser run can get 403 on the document pages; headed capture produced the full gismo graph in this environment.

## Options

### A) HTTP puro

- Lowest runtime cost if tokens can be generated offline.
- Current evidence: gismo data URLs are signed with `T=exp~acl~data~hmac`; no local signer was found in captured payloads.
- Risk: high unless a stable signing endpoint is discovered.

### B) Browser bootstrap + HTTP replay

- Use a headed/headless browser briefly to obtain signed gismo URLs/token and cookies, then replay with `httpx` while valid.
- Runtime cost: medium at startup, low after bootstrap.
- Stability: medium; depends on token TTL and Akamai/header behavior.

### C) Playwright response capture

- Keep the current model: let the browser produce signed requests and capture responses.
- Runtime cost: highest, but most robust against signing changes.
- Stability: currently best known fallback.

## Recommendation

- Recommended path for BetBot research: `B) browser bootstrap + HTTP replay`.
- Keep Playwright response-capture as fallback until token replay proves stable across sessions and expiration windows.
- Do not integrate into production until replay has been validated on sport, tournament, fixtures, and match pages across multiple runs.
