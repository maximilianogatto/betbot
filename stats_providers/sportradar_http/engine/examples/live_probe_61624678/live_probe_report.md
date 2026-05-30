# Sportradar Live Probe Report

- Generated at: `2026-05-26T21:31:54.659849+00:00`
- Poll count: `2`

## Polls

- poll=0 at=`2026-05-26T21:31:51.835034+00:00` status=`Ended` score=`1-2` timeline_events=`192` delta_events=`0` situation_samples=`101`
- poll=1 at=`2026-05-26T21:31:54.658044+00:00` status=`Ended` score=`1-2` timeline_events=`192` delta_events=`0` situation_samples=`101`

## Interpretation

- `match_timeline` is the full event stream snapshot.
- `match_timelinedelta` is the delta feed candidate for lightweight live polling.
- `stats_match_situation` exposes pressure-like samples: attack/dangerous/safe buckets.
- Ended matches normally show zero delta events; live matches are expected to change over polls.

## Client Metrics

```json
{
  "total_requests": 10,
  "success_count": 10,
  "retry_count": 0,
  "refresh_count": 0,
  "blocked_count": 0,
  "expired_count": 0,
  "empty_count": 0,
  "invalid_json_count": 0,
  "http_error_count": 0,
  "endpoint_timings_ms": {
    "match_info_statshub": [
      538.18,
      350.87
    ],
    "stats_match_get": [
      465.33,
      299.73
    ],
    "match_timeline": [
      767.38,
      425.42
    ],
    "match_timelinedelta": [
      1317.6,
      418.05
    ],
    "stats_match_situation": [
      352.46,
      294.9
    ]
  },
  "endpoint_timing_summary": {
    "match_info_statshub": {
      "count": 2,
      "min_ms": 350.87,
      "max_ms": 538.18,
      "avg_ms": 444.52
    },
    "stats_match_get": {
      "count": 2,
      "min_ms": 299.73,
      "max_ms": 465.33,
      "avg_ms": 382.53
    },
    "match_timeline": {
      "count": 2,
      "min_ms": 425.42,
      "max_ms": 767.38,
      "avg_ms": 596.4
    },
    "match_timelinedelta": {
      "count": 2,
      "min_ms": 418.05,
      "max_ms": 1317.6,
      "avg_ms": 867.82
    },
    "stats_match_situation": {
      "count": 2,
      "min_ms": 294.9,
      "max_ms": 352.46,
      "avg_ms": 323.68
    }
  }
}
```
