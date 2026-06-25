"""Helpers for resource monitor remediation actions."""

from __future__ import annotations

from collections.abc import Iterable
import inspect
import logging
from typing import Any

from core.registry import extractor_registry

logger = logging.getLogger(__name__)


async def request_chromium_restart(application: Any | None, *, reason: str) -> int:
    """Ask registered browser runtimes to restart at their next safe point.

    The resource monitor must not kill Chromium processes. Browser-backed
    runtimes expose `request_restart(reason=...)`; `BrowserHandler` then waits
    until active_pages == 0 before the actual stop/start happens.
    """

    requested = 0
    seen: set[int] = set()
    for target in _iter_restart_targets(application):
        if target is None:
            continue
        target_id = id(target)
        if target_id in seen:
            continue
        seen.add(target_id)
        method = getattr(target, "request_restart", None)
        if not callable(method):
            continue
        result = method(reason=reason)
        if inspect.isawaitable(result):
            await result
        requested += 1

    if requested == 0:
        logger.warning("Chromium RAM recovery requested but no graceful restart target is registered.")
    return requested


def _iter_restart_targets(application: Any | None) -> Iterable[Any]:
    bot_data = getattr(application, "bot_data", {}) if application is not None else {}
    if isinstance(bot_data, dict):
        yield bot_data.get("browser_handler")
        registry = bot_data.get("extractor_registry")
        if registry is not None:
            yield from _iter_registry_targets(registry)

    yield from _iter_registry_targets(extractor_registry)


def _iter_registry_targets(registry: Any) -> Iterable[Any]:
    list_registered = getattr(registry, "list_registered", None)
    if not callable(list_registered):
        return
    for extractor in list_registered():
        yield extractor
        for attr_name in ("browser_handler", "_browser_handler"):
            yield getattr(extractor, attr_name, None)
        client = getattr(extractor, "_client", None)
        if client is not None:
            for attr_name in ("browser_handler", "_browser_handler"):
                yield getattr(client, attr_name, None)
