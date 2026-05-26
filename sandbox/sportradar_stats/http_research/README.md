# Statshub / Sportradar HTTP Research

Research-only tooling to understand whether Statshub/Bet365Stats network calls
can be replayed with HTTP directly.

No production package, database, bot handler, or extractor imports this folder.

## Capture Browser Evidence

Headed mode is recommended because headless Chromium may receive Akamai
`403 Access Denied` on Statshub pages in this environment.

```bash
./betbot/bin/python sandbox/sportradar_stats/http_research/capture_statshub.py \
  --default-set \
  --headed \
  --seconds 12 \
  --out-dir sandbox/sportradar_stats/http_research/captures/base_set
```

Outputs:

- `requests.ndjson`
- `responses.ndjson`
- `fetch_only.ndjson`
- `endpoints_index.json`
- `endpoint_report.md`
- `endpoint_catalog.md`
- `cookies.json`
- `script_hints.json`
- `token_analysis.md`
- `api_feasibility.md` after replay probes

## Probe HTTP Replay

```bash
./betbot/bin/python sandbox/sportradar_stats/http_research/http_probe.py \
  --capture-dir sandbox/sportradar_stats/http_research/captures/base_set \
  --cookies-json sandbox/sportradar_stats/http_research/captures/base_set/cookies.json \
  --out-dir sandbox/sportradar_stats/http_research/captures/base_set
```

## Probe Token Reuse

```bash
./betbot/bin/python sandbox/sportradar_stats/http_research/token_replay_probe.py \
  sandbox/sportradar_stats/http_research/captures/base_set
```

## Build Final Feasibility Report

```bash
./betbot/bin/python sandbox/sportradar_stats/http_research/build_feasibility_report.py \
  sandbox/sportradar_stats/http_research/captures/base_set
```

## Interpretation

- Direct page URLs can be fetched as documents, but gismo API data is signed.
- The `T` query parameter contains `exp`, `acl`, `data`, and `hmac`.
- `data` is base64 JSON; observed payloads include origin/client metadata.
- This sandbox determines whether captured signed URLs can be replayed and
  whether the same signed token survives path/ID mutation.
- Current evidence favors a browser-bootstrap + HTTP-replay architecture:
  use the browser to obtain valid signed `/gismo/` URLs, then replay them with
  HTTP while the token is valid.
- Minimal replay headers matter. Requests without `origin`/`referer` can return
  HTTP 200 with a small JSON exception body instead of the useful payload.
