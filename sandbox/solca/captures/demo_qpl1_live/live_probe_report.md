# Betby Live Probe

- Platform: `betby_demo`
- Feed: `live`
- Tournament id: `1899821103254212608`
- League: `None`
- Country: `None`
- Snapshot endpoint: `https://demoapi.betby.com/api/v4/live/brand/1653815133341880320/en/0`
- Chunks: `2`
- Matches in live feed: `0`
- Currently live: `0`

## Matches

- No target tournament events were present in the live snapshot.

## Conclusion

- `version=0` on `/api/v4/live/brand/...` returns the same manifest/chunk pattern as prematch.
- `state.status == 1` and/or `state.clock` are usable first-pass live signals.
- The sandbox keeps `raw_state` because match status code meanings still need mapping per sport/provider.
