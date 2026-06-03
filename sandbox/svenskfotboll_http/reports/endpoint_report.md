# Svenskfotboll Endpoint Report

## Feasibility

Svenskfotboll can be used as a lightweight HTTP stats provider for Swedish football data.

The strongest path is not the protected HTML detail pages. It is:

1. Discover competitions with `comp-find`.
2. Pull standings/fixtures/results through the official widget endpoint.
3. Pull live state and event data through FOGIS XML.

## Endpoints

| Purpose | Endpoint | Format | Browser needed | Notes |
| --- | --- | --- | --- | --- |
| Competition discovery | `/api/comp-find/filter` | JSON | No | Large full tree, filter client-side. |
| Filter criteria | `/api/comp-find/getfiltercriteria` | JSON | No | District/association/gender/age metadata. |
| Matches today | `/api/matches-today/games/?associationId=1&dateOffset=0` | JSON | No | Daily fixture scan by association. |
| Live ticker | `/api/livescore-ticker/` | JSON | No | Fast score/live state overview. |
| League table | `/widget.aspx?p=1&scr=tablesmall&ftid=<id>` | JSON with HTML table | No | Parse HTML rows. |
| Upcoming fixtures | `/widget.aspx?p=1&scr=cominginleague&ftid=<id>&nbr=<n>` | JSON with HTML table | No | Includes match ids in row links. |
| Latest results | `/widget.aspx?p=1&scr=latestinleague&ftid=<id>&nbr=<n>` | JSON with HTML table | No | Includes scores and match ids. |
| Live overview | `https://c01.fogis.se/fogistemplates.se/livescore/xml/overview-1-YYYYMMDD.xml` | XML | No | Full daily live overview. |
| Live game info | `https://c01.fogis.se/fogistemplates.se/livescore/xml/game-info-<match_id>.xml` | XML | No | Score, status, stats, goals, corners, red card stats/events. |
| Live lineups | `https://c01.fogis.se/fogistemplates.se/livescore/xml/lineup-<match_id>.xml` | XML | No | Players, formations, player stats. |
| Live changed files | `https://c01.fogis.se/fogistemplates.se/livescore/xml/changes-1.xml` | XML | No | Polling index for changed game/lineup XML. |

## Blocked/Not Recommended

- `/go-to/?ftid=<id>`
- `/go-to/?fmid=<id>`
- `/serier-cuper/tabell-och-resultat/...`
- `/matchfakta/...`

These pages returned Cloudflare challenge responses through plain HTTP and headless Playwright. The HTTP provider should avoid them.

## Provider Recommendation

Build a provider that uses only the endpoints above. It should be enough for:

- league search
- fixture listing
- standings
- recent results
- live score and events where FOGIS coverage exists

It is not an odds provider. It is a stats/fixtures/live-state provider for Swedish football.

