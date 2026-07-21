"""Renderers de Telegram: convierten datos de dominio en mensajes HTML.

Esta es la capa de presentación (PR2-E3). Nada de acá debe importarse desde
`core/`, `adapters/` ni los services: la dependencia va en un solo sentido
(interfaces → core), nunca al revés.

Vivía en `bot/alerts.py`. La lógica de dominio que estaba mezclada ahí
(identidad/agrupado de partidos) se movió a `core/match_identity.py`.
"""
from __future__ import annotations

from interfaces.telegram.renderers.messages import (
    # Alertas
    build_new_event_alert_message,
    build_grouped_new_event_alert_message,
    build_odds_change_alert_message,
    build_grouped_odds_change_alert_message,
    build_match_reminder_alert_message,
    build_competition_unavailable_warning_message,
    build_little_changes_message,
    # Partidos
    build_match_card_message,
    build_comparison_match_card_message,
    build_all_matches_message,
    # Links
    build_competition_url_message,
    build_event_url_message,
    build_grouped_event_url_message,
    build_event_stats_message,
    # Formato
    format_kickoff_text,
    format_kickoff_labels,
    format_display_datetime,
    format_odd_text,
    split_telegram_message,
    # Re-export de dominio (definido en core/match_identity.py)
    group_events_by_physical_match,
)

__all__ = [
    "build_new_event_alert_message",
    "build_grouped_new_event_alert_message",
    "build_odds_change_alert_message",
    "build_grouped_odds_change_alert_message",
    "build_match_reminder_alert_message",
    "build_competition_unavailable_warning_message",
    "build_little_changes_message",
    "build_match_card_message",
    "build_comparison_match_card_message",
    "build_all_matches_message",
    "build_competition_url_message",
    "build_event_url_message",
    "build_grouped_event_url_message",
    "build_event_stats_message",
    "format_kickoff_text",
    "format_kickoff_labels",
    "format_display_datetime",
    "format_odd_text",
    "split_telegram_message",
    "group_events_by_physical_match",
]
