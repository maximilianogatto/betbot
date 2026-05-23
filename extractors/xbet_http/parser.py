"""Defensive parsers for 1xBet-compatible LineFeed responses."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from core.extractor_base import CompetitionUnavailableError
from core.models import CompetitionExtraction, CompetitionKey, EventKey, EventSnapshot, Odds1X2
from core.models import utc_now_iso
from extractors.xbet_http.models import XBetFixture, XBetLeagueSnapshot

PLATFORM = "1xbet_http"


def parse_champ_zip_payload(
    payload: dict[str, Any],
    *,
    source_url: str,
    event_url_builder: Callable[[str], str | None] | None = None,
) -> CompetitionExtraction:
    """Parse `GetChampZip` into the bot's generic competition model."""

    snapshot = parse_champ_zip_snapshot(payload, source_url=source_url)
    competition_key = CompetitionKey(
        platform=snapshot.platform,
        competition_external_id=snapshot.league_id,
    )
    events = [
        _fixture_to_event_snapshot(
            fixture,
            snapshot=snapshot,
            event_url_builder=event_url_builder,
        )
        for fixture in snapshot.fixtures
    ]

    return CompetitionExtraction(
        competition=competition_key,
        competition_name=snapshot.league_name,
        source_url=snapshot.source_url,
        events=events,
        is_empty=not events,
        is_provisional_name=False,
        extracted_at=snapshot.extracted_at,
        metadata={
            "sport_id": snapshot.sport_id,
            "country": snapshot.country,
            "source": "GetChampZip",
        },
        raw_payload=snapshot.raw_payload,
    )


def parse_champ_zip_snapshot(payload: dict[str, Any], *, source_url: str) -> XBetLeagueSnapshot:
    if payload.get("Success") is False:
        raise CompetitionUnavailableError(
            str(payload.get("Error") or "1xBet GetChampZip returned Success=false."),
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
            details={"error_code": payload.get("ErrorCode")},
        )

    value = payload.get("Value")
    if not isinstance(value, dict):
        raise CompetitionUnavailableError(
            "1xBet GetChampZip response did not include a league object.",
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
        )

    league_id = _safe_str(value.get("LI"))
    league_name = _safe_str(value.get("L"))
    if league_id is None:
        raise CompetitionUnavailableError(
            "1xBet GetChampZip response did not include LI.",
            platform=PLATFORM,
            source_url=source_url,
            reason_code="competition_unavailable",
        )

    extracted_at = utc_now_iso()
    fixtures = [
        fixture
        for raw_game in value.get("G") or []
        for fixture in [_parse_fixture(raw_game, fallback_country=value.get("CN"))]
        if fixture is not None
    ]

    return XBetLeagueSnapshot(
        platform=PLATFORM,
        source_url=source_url,
        league_id=league_id,
        league_name=league_name or f"1xBet liga {league_id}",
        sport_id=_safe_str(value.get("SI")),
        country=_safe_str(value.get("CN")),
        extracted_at=extracted_at,
        fixtures=fixtures,
        raw_payload={
            "source": "GetChampZip",
            "league_id": league_id,
            "league_name": league_name,
            "sport_id": _safe_str(value.get("SI")),
            "country": _safe_str(value.get("CN")),
            "events_count": len(fixtures),
        },
    )


def _parse_fixture(raw_game: object, *, fallback_country: object | None) -> XBetFixture | None:
    if not isinstance(raw_game, dict):
        return None

    event_id = _safe_str(raw_game.get("I"))
    home = _safe_str(raw_game.get("O1"))
    away = _safe_str(raw_game.get("O2"))
    if event_id is None or home is None or away is None:
        return None

    start_time_unix, start_time_utc, label_date, label_time = _parse_start_time(raw_game.get("S"))
    raw_payload = {
        "event_id": event_id,
        "game_code": _safe_str(raw_game.get("N")),
        "competition_id": _safe_str(raw_game.get("CI")),
        "home_id": _safe_str(raw_game.get("O1I")),
        "away_id": _safe_str(raw_game.get("O2I")),
        "country": _safe_str(raw_game.get("CE") or fallback_country),
        "source": "GetChampZip",
    }

    return XBetFixture(
        event_id=event_id,
        home=home,
        away=away,
        start_time_unix=start_time_unix,
        start_time_utc=start_time_utc,
        label_date=label_date,
        label_time=label_time,
        home_id=_safe_str(raw_game.get("O1I")),
        away_id=_safe_str(raw_game.get("O2I")),
        raw_payload=raw_payload,
    )


def _fixture_to_event_snapshot(
    fixture: XBetFixture,
    *,
    snapshot: XBetLeagueSnapshot,
    event_url_builder: Callable[[str], str | None] | None,
) -> EventSnapshot:
    event_url = event_url_builder(fixture.event_id) if event_url_builder is not None else None
    raw_payload = {
        **fixture.raw_payload,
        "league_id": snapshot.league_id,
        "league_name": snapshot.league_name,
        "sport_id": snapshot.sport_id,
        "country": snapshot.country or fixture.raw_payload.get("country"),
    }

    return EventSnapshot(
        key=EventKey(
            platform=snapshot.platform,
            competition_external_id=snapshot.league_id,
            external_event_id=fixture.event_id,
        ),
        competition_name=snapshot.league_name,
        home=fixture.home,
        away=fixture.away,
        scheduled_label_date=fixture.label_date,
        scheduled_label_time=fixture.label_time,
        scheduled_at=fixture.start_time_utc,
        source_url=event_url,
        odds_1x2=Odds1X2(home=None, draw=None, away=None),
        extracted_at=snapshot.extracted_at,
        markets_payload=None,
        metadata={
            "home_id": fixture.home_id,
            "away_id": fixture.away_id,
        },
        raw_payload=raw_payload,
    )


def _parse_start_time(value: object | None) -> tuple[int | None, str | None, str | None, str | None]:
    if value in (None, ""):
        return None, None, None, None

    try:
        start_time_unix = int(float(str(value)))
    except (TypeError, ValueError):
        return None, None, None, None

    kickoff = datetime.fromtimestamp(start_time_unix, tz=UTC)
    return (
        start_time_unix,
        kickoff.isoformat(),
        kickoff.date().isoformat(),
        kickoff.strftime("%H:%M"),
    )


def _safe_str(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
