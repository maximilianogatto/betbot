"""Local JSON persistence for tracked targets.

This module implements the simplest persistence layer used by the project:
tracks are stored in a JSON file under `data/tracks.json`, grouped by
Telegram `chat_id`.

The storage layer is intentionally separate from Telegram handlers and from
monitoring logic. Handlers call `TrackerService`, and that service uses the
functions in this module to read and write data.

Current design notes:
    - Storage is file-based because it is easy to inspect while learning.
    - Data is organized by chat so each Telegram conversation keeps its own
      tracked targets.
    - This approach is sufficient for local development, but a future version
      could evolve to SQLite or another database for concurrency and richer
      queries.
"""

from dataclasses import asdict, dataclass
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
TRACKS_FILE_PATH = DATA_DIR / "tracks.json"


@dataclass(frozen=True)
class TrackTarget:
    """Represent a single tracked item stored for one Telegram chat.

    Attributes:
        type (str): Category of the tracked target, such as `"league"` or
            `"event"`.
        key (str): Normalized identifier for the tracked target, such as
            `"premier_league"`.

    Notes:
        This structure is used both by the storage layer and by
        `monitors.tracker.TrackerService` when formatting responses.
    """

    type: str
    key: str


def add_track(chat_id: int, target_type: str, key: str) -> bool:
    """Add a new tracking target for a specific Telegram chat.

    This function persists a new track configuration associated with the
    provided chat identifier. It is used by the `/track` command flow, through
    `TrackerService`, to remember which leagues or events the bot should
    monitor in the future.

    Args:
        chat_id (int): Unique Telegram chat identifier where the command was
            issued.
        target_type (str): Type of tracked target, for example `"league"` or
            `"event"`.
        key (str): Internal identifier for the tracked target, such as
            `"premier_league"` or `"arsenal_vs_chelsea"`.

    Returns:
        bool: `True` if the target was added successfully, `False` if it
        already existed.

    Side Effects:
        Updates the local JSON file used to store tracked targets.

    Notes:
        This module assumes validation was already performed upstream by
        `monitors.tracker.TrackerService`.
    """

    data = _load_storage()
    chat_entry = _get_or_create_chat_entry(data["chats"], chat_id)

    if _target_exists(chat_entry["targets"], target_type, key):
        logger.info(
            "Track ya existente para chat_id=%s, type=%s, key=%s.",
            chat_id,
            target_type,
            key,
        )
        return False

    # Persist the new track using a serializable dictionary derived from the
    # dataclass. Sorting keeps the file stable and easier to inspect manually.
    chat_entry["targets"].append(asdict(TrackTarget(type=target_type, key=key)))
    chat_entry["targets"].sort(key=lambda item: (item["type"], item["key"]))
    _save_storage(data)

    logger.info(
        "Track agregado para chat_id=%s, type=%s, key=%s.",
        chat_id,
        target_type,
        key,
    )
    return True


def remove_track(chat_id: int, target_type: str, key: str) -> bool:
    """Remove a stored tracking target from a specific Telegram chat.

    This function is the persistence counterpart of the `/untrack` command. It
    removes a target matching the provided `(type, key)` pair for the given
    `chat_id`.

    Args:
        chat_id (int): Telegram chat identifier whose stored tracks will be
            inspected.
        target_type (str): Type of target to remove.
        key (str): Normalized key of the target to remove.

    Returns:
        bool: `True` if a matching track existed and was removed, `False`
        otherwise.

    Side Effects:
        May rewrite the local JSON storage file. If a chat ends up with no
        targets, its entry is removed entirely to keep the file clean.
    """

    data = _load_storage()
    chats = data["chats"]

    for chat_entry in chats:
        if chat_entry["chat_id"] != chat_id:
            continue

        original_count = len(chat_entry["targets"])
        # Iterate with index to allow deletion. This assumes that `(type, key)` pairs are unique within a chat, which is guaranteed by `add_track()`.
        for i, target in enumerate(chat_entry["targets"]):
            if target["type"] == target_type and target["key"] == key:
                del chat_entry["targets"][i]
                break

        if len(chat_entry["targets"]) == original_count:
            logger.info(
                "No se encontró track para eliminar en chat_id=%s, type=%s, key=%s.",
                chat_id,
                target_type,
                key,
            )
            return False

        if not chat_entry["targets"]:
            chats.remove(chat_entry)

        _save_storage(data)
        logger.info(
            "Track eliminado para chat_id=%s, type=%s, key=%s.",
            chat_id,
            target_type,
            key,
        )
        return True

    logger.info(
        "No hay tracks guardados para chat_id=%s al intentar eliminar type=%s, key=%s.",
        chat_id,
        target_type,
        key,
    )
    return False


def list_tracks(chat_id: int) -> list[TrackTarget]:
    """Return all stored targets for a specific Telegram chat.

    Args:
        chat_id (int): Telegram chat identifier whose tracks should be loaded.

    Returns:
        list[TrackTarget]: All tracked targets for the chat. Returns an empty
        list when the chat has no saved configuration yet.

    Notes:
        This function is used by `TrackerService.list_targets()` to implement
        the `/list_tracks` command.
    """

    data = _load_storage()

    for chat_entry in data["chats"]:
        if chat_entry["chat_id"] == chat_id:
            return [
                TrackTarget(type=target["type"], key=target["key"])
                for target in chat_entry["targets"]
            ]

    return []


def _load_storage() -> dict[str, list[dict[str, object]]]:
    """Load and validate the JSON storage file.

    Returns:
        dict[str, list[dict[str, object]]]: Parsed storage structure with a top
        level `"chats"` list.

    Side Effects:
        Ensures the storage file exists before attempting to read it.

    Raises:
        ValueError: If the file exists but does not contain valid JSON or does
            not follow the expected structure.

    Notes:
        Validation is intentionally lightweight. For this learning stage, the
        goal is to keep the storage format explicit and easy to debug by hand.
    """

    _ensure_storage_file()

    try:
        raw_text = TRACKS_FILE_PATH.read_text(encoding="utf-8").strip()
        if not raw_text:
            return {"chats": []}

        data = json.loads(raw_text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"El archivo de tracks no tiene JSON válido: {TRACKS_FILE_PATH}"
        ) from error

    if not isinstance(data, dict) or "chats" not in data or not isinstance(data["chats"], list):
        raise ValueError(
            "La estructura del archivo de tracks es inválida. Se esperaba {'chats': [...]}."
        )

    return data


def _save_storage(data: dict[str, list[dict[str, object]]]) -> None:
    """Persist the full in-memory storage structure to disk.

    Args:
        data (dict[str, list[dict[str, object]]]): Storage payload to serialize
            as JSON.

    Returns:
        None: The function writes the file and does not return data.

    Side Effects:
        Rewrites `data/tracks.json`.

    Notes:
        The entire file is rewritten on each change. This is acceptable for a
        small local project and keeps the persistence code simple to study.
    """

    _ensure_storage_file()
    TRACKS_FILE_PATH.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _ensure_storage_file() -> None:
    """Create the data directory and JSON file if they do not exist yet.

    Returns:
        None: The function prepares the filesystem as needed.

    Side Effects:
        May create the `data/` directory and initialize `tracks.json` with an
        empty structure.

    Notes:
        This makes the first `/track` command work without any manual setup
        beyond running the bot.
    """

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not TRACKS_FILE_PATH.exists():
        TRACKS_FILE_PATH.write_text(
            json.dumps({"chats": []}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _get_or_create_chat_entry(
    chats: list[dict[str, object]],
    chat_id: int,
) -> dict[str, object]:
    """Return the storage entry for a chat, creating it if necessary.

    Args:
        chats (list[dict[str, object]]): Mutable list of chat entries loaded
            from the JSON structure.
        chat_id (int): Telegram chat identifier to find or create.

    Returns:
        dict[str, object]: Storage dictionary for the target chat.

    Side Effects:
        May append a new chat entry to the `chats` list.
    """

    for chat_entry in chats:
        if chat_entry["chat_id"] == chat_id:
            return chat_entry

    # New chats start with an empty target list. Sorting by `chat_id` keeps the
    # file deterministic and easier to compare in version control or debugging.
    chat_entry = {"chat_id": chat_id, "targets": []}
    chats.append(chat_entry)
    chats.sort(key=lambda item: item["chat_id"])
    return chat_entry


def _target_exists(targets: list[dict[str, str]], target_type: str, key: str) -> bool:
    """Check whether a target already exists inside one chat entry.

    Args:
        targets (list[dict[str, str]]): Existing stored targets for a chat.
        target_type (str): Type of target being searched.
        key (str): Key of the target being searched.

    Returns:
        bool: `True` if the target already exists, `False` otherwise.
    """

    return any(
        target["type"] == target_type and target["key"] == key
        for target in targets
    )
