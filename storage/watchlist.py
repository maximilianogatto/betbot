"""Local JSON persistence for weekly watchlist matches.

This module stores the current watchlist for each Telegram chat in a local
JSON file. The watchlist is a separate persistence concern from tracked
targets:

- `storage.tracks` remembers *what to follow*.
- `storage.watchlist` remembers *which fixtures were selected* after analysis.

Keeping the watchlist in its own storage file makes the future roadmap easier:
later stages can enrich saved fixtures with odds information and alert flags
without touching tracked league configuration.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
WATCHLIST_FILE_PATH = DATA_DIR / "watchlists.json"


@dataclass(frozen=True)
class WatchlistMatch:
    """Represent one candidate fixture saved in the weekly watchlist.

    Attributes:
        fixture_id (str): Stable identifier for the fixture in the current data
            provider.
        league_code (str): Internal league identifier, for example
            `"premier_league"`.
        league_name (str): Human-readable league name shown to the user.
        home_team (str): Home team name.
        away_team (str): Away team name.
        kickoff_at (str): Fixture date/time stored as an ISO-formatted string.
        imbalance_score (float): Score from 0 to 100 representing how uneven
            the matchup looks from the available standings data.
        reasons (list[str]): Human-readable reasons explaining why the fixture
            was selected.
        odds_seen (bool): Flag reserved for a future odds provider stage.
        alert_sent (bool): Flag reserved for future Telegram alerting jobs.
    """

    fixture_id: str
    league_code: str
    league_name: str
    home_team: str
    away_team: str
    kickoff_at: str
    imbalance_score: float
    reasons: list[str]
    odds_seen: bool = False
    alert_sent: bool = False


def save_watchlist(chat_id: int, matches: list[WatchlistMatch]) -> None:
    """Persist a new weekly watchlist for a specific Telegram chat.

    Args:
        chat_id (int): Telegram chat whose watchlist should be replaced.
        matches (list[WatchlistMatch]): Watchlist entries produced by the
            builder for the current analysis cycle.

    Returns:
        None: The function writes the watchlist snapshot to disk.

    Side Effects:
        Creates or updates the local JSON persistence file.

    Notes:
        Each save fully replaces the previous watchlist for the chat so the
        stored data always represents the latest weekly build.
    """

    data = _load_storage()
    chat_entry = _get_or_create_chat_entry(data["chats"], chat_id)
    chat_entry["generated_at"] = datetime.now(timezone.utc).isoformat()
    chat_entry["matches"] = [asdict(match) for match in matches]
    _save_storage(data)

    logger.info(
        "Watchlist saved for chat_id=%s with %s matches.",
        chat_id,
        len(matches),
    )


def load_watchlist(chat_id: int) -> list[WatchlistMatch]:
    """Load the saved watchlist for a Telegram chat.

    Args:
        chat_id (int): Telegram chat whose watchlist should be loaded.

    Returns:
        list[WatchlistMatch]: Saved watchlist entries for the chat. Returns an
        empty list if no watchlist has been built yet.
    """

    data = _load_storage()

    for chat_entry in data["chats"]:
        if chat_entry["chat_id"] != chat_id:
            continue

        return [_match_from_dict(match) for match in chat_entry["matches"]]

    return []


def clear_watchlist(chat_id: int) -> None:
    """Remove the saved watchlist for a Telegram chat.

    Args:
        chat_id (int): Telegram chat whose watchlist should be removed.

    Returns:
        None: The function updates the persistence file in place.

    Side Effects:
        May remove one chat entry from the watchlist storage file.
    """

    data = _load_storage()
    original_count = len(data["chats"])
    data["chats"] = [
        chat_entry for chat_entry in data["chats"] if chat_entry["chat_id"] != chat_id
    ]

    if len(data["chats"]) == original_count:
        return

    _save_storage(data)
    logger.info("Watchlist cleared for chat_id=%s.", chat_id)


def _load_storage() -> dict[str, list[dict[str, object]]]:
    """Load and validate the JSON watchlist storage file."""

    _ensure_storage_file()

    try:
        raw_text = WATCHLIST_FILE_PATH.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {"chats": []}

        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"El archivo de watchlist no tiene JSON válido: {WATCHLIST_FILE_PATH}"
        ) from error

    if not isinstance(data, dict) or "chats" not in data or not isinstance(data["chats"], list):
        raise ValueError(
            "La estructura del archivo de watchlist es inválida. Se esperaba {'chats': [...]}."
        )

    return data


def _save_storage(data: dict[str, list[dict[str, object]]]) -> None:
    """Write the in-memory watchlist storage structure back to disk."""

    _ensure_storage_file()
    WATCHLIST_FILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _ensure_storage_file() -> None:
    """Create the data directory and JSON file if they do not exist yet."""

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not WATCHLIST_FILE_PATH.exists():
        WATCHLIST_FILE_PATH.write_text(
            json.dumps({"chats": []}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _get_or_create_chat_entry(
    chats: list[dict[str, object]],
    chat_id: int,
) -> dict[str, object]:
    """Return the watchlist storage entry for a chat, creating it if needed."""

    for chat_entry in chats:
        if chat_entry["chat_id"] == chat_id:
            return chat_entry

    chat_entry = {
        "chat_id": chat_id,
        "generated_at": None,
        "matches": [],
    }
    chats.append(chat_entry)
    chats.sort(key=lambda item: item["chat_id"])
    return chat_entry


def _match_from_dict(raw_match: dict[str, object]) -> WatchlistMatch:
    """Convert a raw JSON dictionary into a typed `WatchlistMatch`."""

    return WatchlistMatch(
        fixture_id=str(raw_match["fixture_id"]),
        league_code=str(raw_match["league_code"]),
        league_name=str(raw_match["league_name"]),
        home_team=str(raw_match["home_team"]),
        away_team=str(raw_match["away_team"]),
        kickoff_at=str(raw_match["kickoff_at"]),
        imbalance_score=float(raw_match["imbalance_score"]),
        reasons=[str(reason) for reason in raw_match["reasons"]],
        odds_seen=bool(raw_match["odds_seen"]),
        alert_sent=bool(raw_match["alert_sent"]),
    )
