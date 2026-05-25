# Sportradar / Statshub Discovery Endpoint Report

- Records: `1`
- Endpoints: `1`

## Role Coverage

- `sport`: 1

## Endpoints

### `/bet365/en/sport/:id`

- Count: `1`
- Statuses: `{'403': 1}`
- Roles: `sport=1`
- Paths: `['/bet365/en/sport/:id']`
- Query URLs: `[]`
- ID patterns: `{'path_ids': ['1'], 'query_ids': [], 'payload_ids': []}`
- Top-level keys: `[]`
- Example URL: `https://statshub.sportradar.com/bet365/en/sport/1`

## Initial Conclusions

- Endpoints with `sport`, `league`, `fixture`, `schedule`, or `standings` roles are candidates for browserless discovery.
- Repeated signed URLs with `T=exp=...` should be treated as reusable only within their signature window until HTTP probing confirms otherwise.
- This report intentionally maps API shape only; it does not normalize full fixtures or integrate with BetBot.
