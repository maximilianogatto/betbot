# Betby Live Probe

- Platform: `betby_demo`
- Feed: `live`
- Tournament id: `2622765713244434457`
- League: `Delhi Senior Division`
- Country: `India`
- Snapshot endpoint: `https://demoapi.betby.com/api/v4/live/brand/1653815133341880320/en/0`
- Chunks: `2`
- Matches in live feed: `1`
- Currently live: `1`

## Matches

- Garhwal Diamond vs Garhwal FC | live=True status=1 match_status=7 clock=60:47 1x2=False totals=True handicap=False

## Conclusion

- `version=0` on `/api/v4/live/brand/...` returns the same manifest/chunk pattern as prematch.
- `state.status == 1` and/or `state.clock` are usable first-pass live signals.
- The sandbox keeps `raw_state` because match status code meanings still need mapping per sport/provider.
