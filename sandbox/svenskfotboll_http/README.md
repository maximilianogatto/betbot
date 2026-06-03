# Svenskfotboll HTTP Research

This sandbox investigates whether the Swedish FA site can work like the Finnish Palloliitto provider: lightweight HTTP, no DOM scraping, and enough data for a future BetBot `StatsProvider`.

## Current Finding

Yes, it is feasible for a useful first provider.

What works without browser:

- League discovery: `/api/comp-find/filter`
- Filter metadata: `/api/comp-find/getfiltercriteria`
- Matches today: `/api/matches-today/games/`
- League standings: `/widget.aspx?p=1&scr=tablesmall&ftid=<competition_id>`
- Upcoming league fixtures: `/widget.aspx?p=1&scr=cominginleague&ftid=<competition_id>&nbr=<limit>`
- Latest league results: `/widget.aspx?p=1&scr=latestinleague&ftid=<competition_id>&nbr=<limit>`
- Live ticker: `/api/livescore-ticker/`
- Live XML overview: `https://c01.fogis.se/fogistemplates.se/livescore/xml/overview-1-YYYYMMDD.xml`
- Live game info/events/stats: `https://c01.fogis.se/fogistemplates.se/livescore/xml/game-info-<match_id>.xml`
- Live changes index: `https://c01.fogis.se/fogistemplates.se/livescore/xml/changes-1.xml`

What does not work cleanly:

- `go-to/?ftid=...` and `go-to/?fmid=...` pages are Cloudflare-protected.
- Detail pages should not be used by a lightweight provider.
- Widget endpoints return JSON with embedded HTML tables, so parsing is needed.

## Run Probe

```bash
./betbot/bin/python sandbox/svenskfotboll_http/probe_svenskfotboll.py \
  --query allsvenskan \
  --ftid 133348 \
  --out-dir sandbox/svenskfotboll_http/examples/latest
```

Outputs:

- `leagues.json`
- `league_snapshot.json`
- `live_snapshot.json`
- `endpoint_report.md`

## Data Model Direction

For a future production provider:

- Use `competition_id` as provider league id.
- Use `match_id` / `fmid` as provider fixture id.
- Treat `ftid` and `competition_id` as the same provider-side identifier.
- Use widget fixtures/results for scheduled matches and historical context.
- Use FOGIS XML for live score, events, red cards, corners and shots when coverage exists.

## Implementation Notes

- `client.py` contains the HTTP-only client.
- `normalizers.py` contains pure parsers for JSON, widget HTML and FOGIS XML.
- `probe_svenskfotboll.py` generates real evidence and reports.
- No production registry or DB code is touched in this sandbox.

## Next Step

If we integrate this later, start with a production `stats_providers/svenskfotboll_http` adapter that wraps this client and implements:

- `search_leagues`
- `list_fixtures`
- `build_match_report`
- optional `get_live_match_state`

The first production version should not depend on Cloudflare-protected pages.

