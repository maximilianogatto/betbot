# FootyStats HTTP Research

Isolated research for evaluating [FootyStats](https://footystats.org) as a
future BetBot stats provider. Nothing in this directory imports or modifies
production collectors, Telegram handlers, storage, or the database.

## Source Contracts

FootyStats exposes three different surfaces. They must not be treated as if
they had the same stability:

| Surface | Example | Browser required | Format | Intended use |
| --- | --- | --- | --- | --- |
| Public page | `https://footystats.org/australia/northern-nsw-npl` | No | HTML | Discovery and research fallback |
| Public AJAX | `https://footystats.org/ajax_livescore.php` | No | JSON or HTML | Lightweight live research |
| Official API | `https://api.football-data-api.com/league-matches?...` | No | JSON | Preferred production candidate with licensed key |

Public-page requests should stay minimal. During the June 1, 2026 probe,
ordinary `httpx` GET requests returned `200`, while adding synthetic
browser-like headers consistently triggered Cloudflare `403` responses.
Headless and headed Playwright captures also reached the Cloudflare challenge.
For this provider, a browser is useful only as a diagnostic tool and should
not be part of the runtime design.

The official API documentation is public at
[`/api/documentations`](https://footystats.org/api/documentations). The
documented API includes league lists, today's matches, league statistics,
league matches, teams, players, referees, team recent form, individual match
details with H2H and odds comparison, and tables.

## Commands

Capture compact browser evidence:

```bash
./betbot/bin/python sandbox/footystats_http/capture_traffic.py \
  https://footystats.org/ \
  --seconds 5 \
  --out-dir sandbox/footystats_http/captures/home
```

Replay captured GET requests without Playwright:

```bash
./betbot/bin/python sandbox/footystats_http/probe_http.py \
  sandbox/footystats_http/captures/home
```

Run a compact HTTP-only feasibility check:

```bash
./betbot/bin/python sandbox/footystats_http/run_http_research.py \
  --out-dir sandbox/footystats_http/examples/latest
```

## Outputs

`capture_traffic.py` writes:

- `responses.ndjson`
- `endpoints_index.json`
- `endpoint_report.md`
- `capture_metadata.json`
- `storage_state.json`

`probe_http.py` writes:

- `http_probe_results.json`
- `http_probe_report.md`

`run_http_research.py` writes:

- `http_research_summary.json`
- `http_feasibility_report.md`

Large browser captures are ignored by Git. The compact example summary is
committed so the conclusions remain inspectable.

## Initial Findings

- Public HTML is directly reusable through ordinary HTTP. The homepage embeds
  country-to-league navigation. League pages embed tables, aggregates and
  match-history data. Match pages can embed form, H2H, odds and live stats.
- Minimal HTTP requests are more reliable than browser automation or copied
  browser headers for the tested public pages.
- `ajax_livescore.php` is a small JSON live feed available through plain HTTP.
- Frontend code references additional AJAX routes such as `ajax_matches.php`,
  `ajax_h2h_neo.php`, `ajax_hover_modal_team.php` and
  `ajax_livescore_h2h.php`.
- The official JSON API is the correct candidate for a stable production
  provider if an API key is available. Public HTML/AJAX parsing is useful for
  evaluation and fallback research, but is undocumented and brittle.

## Next Decision

The narrow public fallback has been promoted to
`stats_providers/footystats_http`. It exposes discovery, standings, fixtures
and lightweight live score reports through BetBot's stable provider contract.
The licensed official API remains the next step for richer H2H, odds and
advanced metric normalization.
