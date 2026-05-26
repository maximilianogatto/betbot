# Statshub/Sportradar Endpoint Catalog

- Records: `4`
- Endpoints: `4`

## Classification Coverage

- `sport`: 3
- `league`: 2
- `match`: 1
- `fixtures`: 1

## Endpoints

### `/bet365/en/match/:id`

- Count: `1`
- Statuses: `{'403': 1}`
- Classification: `match=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/match/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/match/61624678`

### `/bet365/en/sport/:id`

- Count: `1`
- Statuses: `{'403': 1}`
- Classification: `sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1`

### `/bet365/en/sport/:id/tournament/:id`

- Count: `1`
- Statuses: `{'403': 1}`
- Classification: `league=1, sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id/tournament/:id']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1/tournament/8`

### `/bet365/en/sport/:id/tournament/:id/fixtures`

- Count: `1`
- Statuses: `{'403': 1}`
- Classification: `fixtures=1, league=1, sport=1`
- Signed token: `False`
- Query URLs: `[]`
- Normalized paths: `['/bet365/en/sport/:id/tournament/:id/fixtures']`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1/tournament/8/fixtures?view=round`

