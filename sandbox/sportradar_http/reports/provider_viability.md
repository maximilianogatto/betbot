# Sportradar HTTP Provider Viability

- Generated: `2026-05-26`
- Scope: `sandbox/sportradar_http`
- Production code touched: no.

## Current Architecture

```text
headed browser bootstrap
  -> signed T token + replay headers
  -> pure HTTP replay client
  -> endpoint wrappers
  -> compact league/match/live snapshots
  -> features + reports
  -> bot_ready adapter
```

The browser is not used for normal refreshes after bootstrap. It is only needed
to obtain or refresh the signed token/context.

## Evidence From Real Runs

- League pipeline for LaLiga season `130805` generated:
  - `league_snapshot.json`
  - `league_features.json`
  - `league_report.md`
- Match pipeline for match `61624678` generated:
  - `match_snapshot.json`
  - `match_features.json`
  - `match_report.md`
- Live probe for match `61624678` generated:
  - `live_probe.ndjson`
  - `live_probe_summary.json`
  - `live_probe_report.md`

Observed live probe result for an ended match:

- `match_timeline`: `192` full events.
- `match_timelinedelta`: `0` delta events.
- `stats_match_situation`: `101` pressure samples.

This is consistent with the expected model: full timeline remains available,
delta feed is useful for live polling but empty after match end.

## What Works

- HTTP replay works for gismo endpoints with:
  - `origin: https://statshub.sportradar.com`
  - `referer: https://statshub.sportradar.com/`
  - signed `T` token
- Endpoint wrappers work for:
  - match metadata
  - match details/statistics
  - match timeline
  - match situation/pressure samples
  - standings/table slices
  - team form/recent matches
  - team scoring/conceding
  - top goals/cards/assists
  - injuries
  - team versus/H2H through `stats_team_versus`
- Compact snapshots keep raw references separate from normalized data.
- Feature definitions are documented in `feature_catalog.md`.
- `bot_ready` exposes stable sandbox interfaces:
  - `get_match_report(match_id)`
  - `get_league_snapshot(tournament_id/season_id)`
  - `get_live_match_state(match_id)`

## Odds Status

`match_markets` is reachable over HTTP replay.

Important caveat: the real match pipeline example used an ended match. For that
match, `match_markets` responded but returned no priced markets:

- `has_odds_endpoint = true`
- `has_priced_odds = false`

This is expected for some ended or unpriced matches. Before using Sportradar as
an odds provider, we still need a prematch/live validation set where
`match_markets` and/or `unified_sport_matches_markets` contain active prices.

## Risks And Limitations

- Headless bootstrap was observed as blocked earlier; headed bootstrap worked.
- Token generation is not implemented and should not be reverse engineered.
- The signed token is reusable across endpoints while valid, but must be
  refreshed when blocked or expired.
- Some endpoints can be intermittently blocked; the HTTP client now refreshes
  once per request on blocked/expired payloads.
- Tournament-to-current-season resolution is still an observed mapping for this
  phase, not a general resolver.
- Current snapshots are compact but not yet production schemas.

## Recommendation For BetBot

Use this path:

1. Keep browser bootstrap isolated.
2. Cache signed session state.
3. Use pure HTTP replay for normal provider operations.
4. Build a production interface around the existing `bot_ready` methods only
   after schemas are stable.
5. Start integration as a stats provider first.
6. Validate odds provider behavior on active prematch/live fixtures before
   replacing any existing odds extractor.

This provider is already promising for stats, reports, and future agent/ML data.
For odds, it is technically reachable but needs a focused active-market test set
before production use.
