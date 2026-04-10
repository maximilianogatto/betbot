from dataclasses import dataclass


@dataclass
class SportsEvent:
    event_id: str
    sport: str
    league: str
    home_team: str
    away_team: str
    starts_at: str


class SportsAPIClient:
    """Base simple para futuros proveedores de datos deportivos."""

    async def fetch_events(self) -> list[SportsEvent]:
        raise NotImplementedError("Implementá fetch_events() en un cliente concreto.")
