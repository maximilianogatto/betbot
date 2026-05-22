from __future__ import annotations

import os
from pathlib import Path


ENV_PROFILE_KEYS = (
    "SPORTRADAR_USER_DATA_DIR",
    "BETBOT_SPORTRADAR_USER_DATA_DIR",
)
DEFAULT_PROFILE_CANDIDATES = (
    Path("/tmp/chrome-sportradar-profile"),
)


def resolve_capture_user_data_dir(explicit: str | None) -> str | None:
    if explicit:
        return str(Path(explicit).expanduser())

    for env_key in ENV_PROFILE_KEYS:
        env_value = os.environ.get(env_key)
        if env_value:
            return str(Path(env_value).expanduser())

    for candidate in DEFAULT_PROFILE_CANDIDATES:
        if candidate.exists():
            return str(candidate)

    return None


__all__ = ["resolve_capture_user_data_dir"]
