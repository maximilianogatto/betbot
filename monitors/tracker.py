"""Tracking domain logic that sits between Telegram handlers and storage.

This module is the first small "domain service" of the project. It validates
user input coming from Telegram commands, normalizes it into a consistent
internal format, and delegates persistence to `storage.tracks`.

It intentionally does not call external sports APIs yet. Its current role is
to prepare a clean internal workflow so future monitoring jobs can rely on a
stable set of tracked targets.
"""

from dataclasses import dataclass
import logging
import re

from storage.tracks import TrackTarget, add_track, list_tracks, remove_track

logger = logging.getLogger(__name__)

VALID_TRACK_TYPES = {"league", "event"}
TRACK_KEY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,99}$")


@dataclass(frozen=True)
class CommandResult:
    """Represent the outcome of a tracking command.

    Attributes:
        ok (bool): Whether the requested operation succeeded logically.
        message (str): Human-readable message that can be shown directly to the
            Telegram user.

    Notes:
        Returning a small result object instead of raw strings helps keep the
        service layer explicit and easy to extend later.
    """

    ok: bool
    message: str


class TrackerService:
    """Coordinate validation, normalization, and persistence of tracked targets.

    This service is used by Telegram handlers such as `/track`, `/list_tracks`,
    and `/untrack`. It exists so the bot layer does not need to know details
    about storage formats or input normalization rules.

    Notes:
        In a larger system, this is the place where more advanced business
        rules could be added before data reaches the storage or monitoring
        layers.
    """

    def add_target(self, chat_id: int, target_type: str, target_key: str) -> CommandResult:
        """Validate and persist a new tracking target.

        Args:
            chat_id (int): Telegram chat identifier that owns the target.
            target_type (str): Raw target type received from the Telegram
                command.
            target_key (str): Raw target key received from the Telegram command.

        Returns:
            CommandResult: Outcome describing whether the target was added and
            what message should be shown to the user.

        Side Effects:
            May write a new target to the JSON storage file through
            `storage.tracks.add_track()`.

        Notes:
            This method is called from the `/track` handler. It is responsible
            for turning free-form Telegram input into the normalized internal
            representation used by the rest of the system.
        """

        normalized_target = self._normalize_target(target_type, target_key)
        if isinstance(normalized_target, CommandResult): # Validation failed, return the error message.
            return normalized_target

        normalized_type, normalized_key = normalized_target
        was_added = add_track(chat_id, normalized_type, normalized_key)

        if not was_added:
            return CommandResult(
                ok=False,
                message=(
                    f"Ya estabas siguiendo este target: {normalized_type} {normalized_key}."
                ),
            )

        logger.info(
            "Tracking activado para chat_id=%s, type=%s, key=%s.",
            chat_id,
            normalized_type,
            normalized_key,
        )
        return CommandResult(
            ok=True,
            message=(
                f"Tracking activado para {normalized_type} {normalized_key}."
            ),
        )

    def remove_target(self, chat_id: int, target_type: str, target_key: str) -> CommandResult:
        """Validate and remove an existing tracking target.

        Args:
            chat_id (int): Telegram chat identifier that owns the target.
            target_type (str): Raw target type received from `/untrack`.
            target_key (str): Raw target key received from `/untrack`.

        Returns:
            CommandResult: Outcome message indicating whether the target was
            removed successfully.

        Side Effects:
            May update the JSON storage file through
            `storage.tracks.remove_track()`.

        Notes:
            This method mirrors `add_target()` so both commands use the same
            normalization and validation rules.
        """

        normalized_target = self._normalize_target(target_type, target_key)
        if isinstance(normalized_target, CommandResult):
            return normalized_target

        normalized_type, normalized_key = normalized_target
        was_removed = remove_track(chat_id, normalized_type, normalized_key)

        if not was_removed:
            return CommandResult(
                ok=False,
                message=(
                    f"No encontré un track guardado para {normalized_type} {normalized_key}."
                ),
            )

        logger.info(
            "Tracking eliminado para chat_id=%s, type=%s, key=%s.",
            chat_id,
            normalized_type,
            normalized_key,
        )
        return CommandResult(
            ok=True,
            message=(
                f"Tracking eliminado para {normalized_type} {normalized_key}."
            ),
        )

    def list_targets(self, chat_id: int) -> CommandResult:
        """Load and format all tracked targets for one chat.

        Args:
            chat_id (int): Telegram chat identifier whose targets should be
                listed.

        Returns:
            CommandResult: User-facing message containing either the saved
            targets or a message indicating that none exist yet.

        Notes:
            This method is used by the `/list_tracks` handler. It formats
            domain data into a readable text representation, but still keeps
            Telegram-specific sending logic in the handler layer.
        """

        targets = list_tracks(chat_id)

        if not targets:
            return CommandResult(
                ok=True,
                message="No tenés tracks guardados todavía.",
            )

        return CommandResult(
            ok=True,
            message=self._build_track_list_message(targets),
        )

    def _normalize_target(
        self,
        target_type: str,
        target_key: str,
    ) -> tuple[str, str] | CommandResult:
        """Normalize and validate a raw tracking target from user input.

        Args:
            target_type (str): Raw type typed by the user.
            target_key (str): Raw key typed by the user.

        Returns:
            tuple[str, str] | CommandResult: A normalized `(type, key)` pair
            when the input is valid, or a `CommandResult` with an error message
            when validation fails.

        Notes:
            Spaces in target keys are converted to underscores so users can
            type more naturally in Telegram while the internal representation
            remains machine-friendly.
        """

        normalized_type = target_type.strip().lower()
        normalized_key = target_key.strip().lower().replace(" ", "_")

        if normalized_type not in VALID_TRACK_TYPES:
            valid_types = ", ".join(sorted(VALID_TRACK_TYPES))
            return CommandResult(
                ok=False,
                message=(
                    f"Tipo inválido: {target_type}. Tipos permitidos: {valid_types}."
                ),
            )

        if not normalized_key:
            return CommandResult(
                ok=False,
                message="El valor del track no puede estar vacío.",
            )

        # The current project intentionally uses a simple identifier format so
        # stored keys remain easy to read and easy to map to future providers.
        if not TRACK_KEY_PATTERN.fullmatch(normalized_key):
            return CommandResult(
                ok=False,
                message=(
                    "El valor del track solo puede tener letras minúsculas, números, "
                    "guiones y guiones bajos."
                ),
            )

        return normalized_type, normalized_key

    def _build_track_list_message(self, targets: list[TrackTarget]) -> str:
        """Build a human-readable message listing tracked targets.

        Args:
            targets (list[TrackTarget]): Stored targets for one Telegram chat.

        Returns:
            str: Multiline text intended to be sent back to the user.

        Notes:
            Formatting happens here instead of the storage layer because
            presentation belongs closer to the application/domain boundary.
        """

        lines = ["Targets que estás siguiendo:"]

        for target in targets:
            lines.append(f"- {target.type}: {target.key}")

        return "\n".join(lines)
