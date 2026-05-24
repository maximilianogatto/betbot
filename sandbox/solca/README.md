# Solcasino / Rainbet Betby HTTP Research

This sandbox investigates Solcasino/Rainbet clones that use Betby `sptpub` prematch feeds.
It is intentionally isolated from the production bot.

## Confirmed HTTP Flow

The current useful endpoint is:

```text
https://api-g-c7818b61-607.sptpub.com/api/v4/prematch/brand/2392759269461204992/en/0
```

`version=0` returns a small manifest with:

- `version`
- `top_events_versions`
- `rest_events_versions`

Each advertised version can be fetched directly:

```text
https://api-g-c7818b61-607.sptpub.com/api/v4/prematch/brand/2392759269461204992/en/<chunk_version>
```

Merging those chunks reconstructs the prematch snapshot with `sports`, `categories`, `tournaments`, and `events`.

## Extract One League

```bash
./betbot/bin/python sandbox/solca/extract_solcasino_league_http.py \
  "https://solcasino.io/sports?bt-path=%2Fsoccer%2Fbrazil%2Fbrasileiro-serie-a-1669818812230406144" \
  --out-dir sandbox/solca/captures/solcasino_brasileiro_serie_a_http \
  --pretty
```

Outputs:

- `manifest.json`
- `chunks_summary.json`
- `league_odds.json`
- `merged_snapshot.json` only with `--save-raw`

## Probe Snapshot / Chunks

```bash
./betbot/bin/python sandbox/solca/probe_betby_snapshot.py \
  "https://solcasino.io/sports?bt-path=%2Fsoccer%2Faustralia%2Fnpl-western-australia-women-1891453782668222464" \
  --out-dir sandbox/solca/captures/solcasino_npl_wa_women_probe
```

Outputs:

- `manifest.json`
- `snapshot_probe.json`
- `snapshot_probe_report.md`

## Market Mapping Observed

- `markets["1"][""]`: 1X2, outcome ids `1`, `2`, `3`.
- `total=<line>` specs: totals. Observed outcome `12` as Over and `13` as Under.
- `hcp=<line>` specs: handicap. Observed outcome ids `1714` and `1715`; the sandbox keeps raw outcome ids and exposes home/away as a transparent assumption for later verification.

## Current Findings

- The feed works browserless for prematch snapshots.
- Solcasino page HTML may be Cloudflare-protected, but the `sptpub` JSON endpoint is directly reachable with normal HTTP headers.
- The Australia NPL Western Australia Women URL currently returns zero prematch matches because the tournament is not present in the current snapshot.
- Brasileiro Serie A validates the flow: current run produced 14 matches with 1X2 and totals.
- Handicap is not always present in the broad prematch snapshot; a future step should investigate whether Betby exposes a per-event deep-market endpoint for hidden Asian Handicap markets.

## Integration Direction

The likely production shape is similar to `1xbet_http`:

1. Discovery: snapshot all tournaments by country/sport from merged chunks.
2. Tracking: store Betby tournament id as `competition_external_id`.
3. Refresh: poll `version=0`, fetch advertised chunks, filter events by tracked tournament ids.
4. Deep markets: add event-detail probing only if we confirm a stable HTTP endpoint for hidden markets.
