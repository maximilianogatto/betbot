# Betby/Sptpub HTTP Probe

- Platform: `solcasino`
- Tournament id: `1669818812230406144`
- Manifest URL: `https://api-g-c7818b61-607.sptpub.com/api/v4/prematch/brand/2392759269461204992/en/0`
- Manifest status: `200`
- Manifest version: `1779609179212`
- Chunks discovered: `5`
- Target matches found: `14`

## Chunks

- version=1779609179212 status=200 bytes=534570 events=445 tournaments=225 target=False
- version=1779609179213 status=200 bytes=490125 events=400 tournaments=197 target=True
- version=1779609179214 status=200 bytes=437424 events=400 tournaments=96 target=True
- version=1779609179215 status=200 bytes=439745 events=400 tournaments=60 target=True
- version=1779609179216 status=200 bytes=230990 events=228 tournaments=25 target=True

## Conclusion

- `version=0` returns a small manifest with `top_events_versions` and `rest_events_versions`.
- Each advertised version is a plain HTTP JSON chunk.
- Merging chunks by top-level dictionaries reconstructs the current prematch snapshot.
- This is enough for lightweight browserless league tracking when the target tournament is present.
