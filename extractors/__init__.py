"""Bootstrap helpers for concrete sportsbook extractors."""

from __future__ import annotations

import logging
from typing import Any

from core.extractor_base import Extractor
from core.registry import ExtractorRegistry
from extractors.bet365 import Bet365Extractor, Bet365ExtractorSettings
from extractors.betovo_http import BetovoHttpExtractor, betovo_is_configured
from extractors.betsson_http import BetssonHttpExtractor, betsson_is_configured
from extractors.betwarrior_http import BetWarriorHttpExtractor, betwarrior_is_configured
from extractors.bz_http import BzHttpExtractor, bz_is_configured
from extractors.mrpunter_http import MrPunterHttpExtractor, mrpunter_is_configured
from extractors.mystake_http import MystakeHttpExtractor, mystake_is_configured
from extractors.solcasino_http import SolcasinoHttpExtractor, solcasino_is_configured
from extractors.xbet_http import XBetHttpExtractor

logger = logging.getLogger(__name__)


def register_default_extractors(
    registry: ExtractorRegistry,
    *,
    settings: Any | None = None,
) -> list[Extractor]:
    """Register the built-in extractor set used by the current bot."""

    browser_enabled = _extractor_browser_enabled(settings)
    disabled = tuple(getattr(settings, "disabled_platforms", ()) or ())
    registered: list[Extractor] = []

    if _should_register_provider(Bet365Extractor, browser_enabled=browser_enabled, disabled_platforms=disabled):
        registered.append(
            registry.register(Bet365Extractor(settings=_build_bet365_settings(settings)))
        )
    if _should_register_provider(XBetHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled):
        registered.append(registry.register(XBetHttpExtractor()))
    # Mystake registers only once a real REST host is configured (MYSTAKE_API_BASE_URL).
    if mystake_is_configured() and _should_register_provider(
        MystakeHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(MystakeHttpExtractor()))
    # Solcasino (Betby/sptpub) registers once a brand id + api host are available.
    if solcasino_is_configured() and _should_register_provider(
        SolcasinoHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(SolcasinoHttpExtractor()))
    # BZ (m.bz.com, Sportradar-id sportsbook) registers once a base URL exists.
    if bz_is_configured() and _should_register_provider(
        BzHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(BzHttpExtractor()))
    # Betovo (Altenar) registers once a frontend host + integration are available.
    if betovo_is_configured() and _should_register_provider(
        BetovoHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(BetovoHttpExtractor()))
    # BetWarrior (Kambi) registers once an api host + offering are available.
    if betwarrior_is_configured() and _should_register_provider(
        BetWarriorHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(BetWarriorHttpExtractor()))
    # MrPunter (FSB) registers once an api host is available.
    if mrpunter_is_configured() and _should_register_provider(
        MrPunterHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(MrPunterHttpExtractor()))
    # Betsson (OBG) registers once a brand id + market code are available.
    if betsson_is_configured() and _should_register_provider(
        BetssonHttpExtractor, browser_enabled=browser_enabled, disabled_platforms=disabled
    ):
        registered.append(registry.register(BetssonHttpExtractor()))

    logger.info(
        "Extractores activos (%d): %s",
        len(registered),
        ", ".join(e.name for e in registered) or "ninguno",
    )
    if disabled:
        logger.info("Plataformas apagadas por BOT_DISABLED_PLATFORMS: %s", ", ".join(disabled))

    return registered


def _should_register_provider(
    extractor: type[Extractor],
    *,
    browser_enabled: bool,
    disabled_platforms: tuple[str, ...] = (),
) -> bool:
    """Return whether a provider can be enabled in the current runtime."""

    if _is_disabled(extractor, disabled_platforms):
        return False
    return browser_enabled or extractor.provider_capabilities.supports_browserless


def _is_disabled(extractor: type[Extractor], disabled_platforms: tuple[str, ...]) -> bool:
    """True si la plataforma está apagada a mano vía BOT_DISABLED_PLATFORMS.

    Se acepta el nombre con y sin el sufijo `_http` para que en la variable de
    entorno valga escribir `bz` o `bz_http` indistintamente.
    """

    if not disabled_platforms:
        return False
    name = str(getattr(extractor, "name", "")).strip().lower()
    if not name:
        return False
    aliases = {name, name.removesuffix("_http")}
    return any(entry.removesuffix("_http") in {a.removesuffix("_http") for a in aliases}
               for entry in disabled_platforms)


def _extractor_browser_enabled(settings: Any | None) -> bool:
    if settings is None:
        return True
    return bool(getattr(settings, "extractor_browser_enabled", True))


def _build_bet365_settings(settings: Any | None) -> Bet365ExtractorSettings | None:
    """Translate generic app settings into the concrete Bet365 extractor config."""

    if settings is None:
        return None

    defaults = Bet365ExtractorSettings()

    return Bet365ExtractorSettings(
        max_parallel_competitions=int(getattr(settings, "extractor_max_parallel_competitions", defaults.max_parallel_competitions)),
        max_parallel_pages=int(getattr(settings, "extractor_max_parallel_pages", defaults.max_parallel_pages)),
        max_parallel_event_pages=int(getattr(settings, "extractor_max_parallel_event_pages", defaults.max_parallel_event_pages)),
        page_reuse_enabled=bool(getattr(settings, "extractor_page_reuse_enabled", defaults.page_reuse_enabled)),
        browser_restart_after_n_refreshes=getattr(
            settings,
            "extractor_browser_restart_after_n_refreshes",
            defaults.browser_restart_after_n_refreshes,
        ),
        browser_restart_idle_ttl_seconds=getattr(
            settings,
            "extractor_browser_restart_idle_ttl_seconds",
            defaults.browser_restart_idle_ttl_seconds,
        ),
        page_load_timeout_ms=int(getattr(settings, "extractor_page_load_timeout_ms", defaults.page_load_timeout_ms)),
        post_load_wait_ms=int(getattr(settings, "extractor_post_load_wait_ms", defaults.post_load_wait_ms)),
        headless=bool(getattr(settings, "extractor_headless", defaults.headless)),
        capture_wait_timeout_ms=int(getattr(settings, "extractor_capture_wait_timeout_ms", defaults.capture_wait_timeout_ms)),
        capture_stable_ms=int(getattr(settings, "extractor_capture_stable_ms", defaults.capture_stable_ms)),
        capture_attempts=int(getattr(settings, "extractor_capture_attempts", defaults.capture_attempts)),
        event_capture_wait_timeout_ms=int(
            getattr(settings, "extractor_event_capture_wait_timeout_ms", defaults.event_capture_wait_timeout_ms)
        ),
        event_capture_stable_ms=int(getattr(settings, "extractor_event_capture_stable_ms", defaults.event_capture_stable_ms)),
        event_capture_attempts=int(getattr(settings, "extractor_event_capture_attempts", defaults.event_capture_attempts)),
        save_debug_payloads=bool(getattr(settings, "extractor_save_debug_payloads", defaults.save_debug_payloads)),
        debug_payload_dir=getattr(settings, "extractor_debug_payload_dir", defaults.debug_payload_dir),
        extract_alternative_markets=bool(
            getattr(settings, "extractor_extract_alternative_markets", defaults.extract_alternative_markets)
        ),
        allow_legacy_fallback=bool(getattr(settings, "bet365_allow_legacy_fallback", defaults.allow_legacy_fallback)),
    )


__all__ = ["Bet365Extractor", "XBetHttpExtractor", "register_default_extractors"]
