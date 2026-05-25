# Sportradar / Statshub Discovery

Research-only tooling for mapping Statshub navigation APIs without integrating
anything into BetBot production code.

## Capture

```bash
./betbot/bin/python sandbox/sportradar_stats/discovery/capture_discovery.py \
  "https://statshub.sportradar.com/bet365/en/sport/1" \
  --seconds 25 \
  --out-dir sandbox/sportradar_stats/discovery/captures/sport_1_headed \
  --headed
```

In the current macOS/research environment, headless Chromium can receive an
Akamai `403 Access Denied` document for this URL. `--headed` produced usable
XHR/fetch captures.

Optional navigation helpers:

```bash
./betbot/bin/python sandbox/sportradar_stats/discovery/capture_discovery.py \
  "https://statshub.sportradar.com/bet365/en/sport/1" \
  --click-text "Spain" \
  --click-text "LaLiga" \
  --auto-click-links \
  --out-dir sandbox/sportradar_stats/discovery/captures/sport_1_nav
```

The capturer stores only useful `fetch` / `xhr` / Statshub document responses
from Sportradar hosts and ignores JS, CSS, images, fonts, and other static
assets.

## Analyze Existing Capture

```bash
./betbot/bin/python sandbox/sportradar_stats/discovery/analyze_discovery.py \
  sandbox/sportradar_stats/discovery/captures/sport_1
```

## Outputs

- `discovery_responses.ndjson`: compact records with URL, params, status, endpoint name, ID patterns, roles, and summarized JSON.
- `endpoints_index.json`: grouped endpoints with counts, statuses, roles, ID patterns, and example URLs.
- `discovery_map.json`: role-oriented endpoint map.
- `endpoint_report.md`: Markdown report for human inspection.
- `capture_metadata.json`: run metadata and navigation actions.

## Scope

This sandbox maps API shape only:

- sport navigation
- league/tournament discovery
- fixture/schedule endpoints
- standings/table endpoints
- match endpoint links

It does not normalize full fixtures, implement live tracking, or touch
`core/`, `bot/`, `extractors/`, `storage/`, or the database.
