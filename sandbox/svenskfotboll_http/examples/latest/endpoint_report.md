# Svenskfotboll HTTP Probe

## Summary

- Discovery works via `/api/comp-find/filter` and `/api/comp-find/getfiltercriteria`.
- League standings, upcoming fixtures and latest results work via `/widget.aspx` with `ftid`.
- Live state works via `/api/livescore-ticker/` plus FOGIS XML under `c01.fogis.se`.
- Detail pages and `go-to` pages are Cloudflare-protected and should not be part of the lightweight provider.

## Query

- query: `allsvenskan`
- ftid: `133348`
- league matches found: `20`

## Useful Endpoints

| Purpose | Endpoint | Payload | Notes |
| --- | --- | --- | --- |
| League discovery | `/api/comp-find/filter` | JSON | Large full tree, client-side filtering. |
| Filter metadata | `/api/comp-find/getfiltercriteria` | JSON | Association/district/gender/age filters. |
| Matches today | `/api/matches-today/games/?associationId=1&dateOffset=0` | JSON | Good for national/today fixture scan. |
| League standings | `/widget.aspx?p=1&scr=tablesmall&ftid=<id>` | JSON + HTML table | Parseable without browser. |
| Upcoming fixtures | `/widget.aspx?p=1&scr=cominginleague&ftid=<id>&nbr=<n>` | JSON + HTML table | Provides `fmid` in row links. |
| Latest results | `/widget.aspx?p=1&scr=latestinleague&ftid=<id>&nbr=<n>` | JSON + HTML table | Provides scores and `fmid`. |
| Live ticker | `/api/livescore-ticker/` | JSON | Quick live/finished/today status. |
| Live overview | `https://c01.fogis.se/.../overview-1-YYYYMMDD.xml` | XML | Full daily live state by association. |
| Live game info | `https://c01.fogis.se/.../game-info-<fmid>.xml` | XML | Events, score, status, aggregate stats. |
| Live changes | `https://c01.fogis.se/.../changes-1.xml` | XML | Polling index for changed game XML files. |

## League Examples

- `115560` Allsvenskan 2024 categories=Allsvenskan herrar
- `123864` Allsvenskan 2025 categories=Allsvenskan herrar
- `133348` Allsvenskan 2026 categories=Allsvenskan herrar
- `131881` F17 Allsvenskan Final 2025 categories=F17-serier
- `123409` F17 Allsvenskan Norra 2025 categories=F17-serier
- `133303` F17 Allsvenskan Norra 2026 categories=F17-serier
- `123408` F17 Allsvenskan Södra 2025 categories=F17-serier
- `133302` F17 Allsvenskan Södra 2026 categories=F17-serier
- `123051` F19 Allsvenskan 2025 categories=F19-serier
- `131381` F19 Allsvenskan 2026 categories=F19-serier

## League Snapshot

- standings teams: `16`
- upcoming matches: `20`
- latest results: `20`

## Live Snapshot

- ticker games: `7`
- live ticker games: `3`
- sample live match id: `6812343`
- sample event summary: `{"goals": 0, "red_cards": 0, "corners": 0, "latest_event": null}`

## Feasibility

This can become a BetBot stats provider for Swedish competitions.
The strongest version is HTTP-only for discovery, fixtures, standings, results and live game XML.
Limitations: league/match detail pages are Cloudflare-protected, and widget tables are HTML inside JSON rather than clean JSON.
