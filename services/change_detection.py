"""Pure-ish tracking helpers for odds comparisons and reminder selection."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from services.models import MarketChangeDetail, SubscriptionOddsAlert
from core.models import (
    ActiveEventRecord,
    CompetitionSubscription,
    EventBaseline,
    TrackedCompetition,
)
from adapters.storage import SqliteStorage

MARKET_TYPE_LABELS = {
    "1x2": "1X2",
    "asian_handicap": "Asian Handicap",
    "goal_line": "Goal Line",
    "alternative_markets": "Mercados alternativos",
}
TRACKING_META_KEY = "__tracking_meta__"
RECENT_SNAPSHOT_HISTORY_SIZE = 4

# Política anti-ruido: solo alertan las CAÍDAS de cuota (corrección de una cuota
# sobreestimada) y solo cuando son sostenidas (varios snapshots confirmados
# seguidos bajando) o bruscas (posible bug). Las subas y los reprices únicos
# van al digest de cambios pequeños sin notificar.
SUSTAINED_DROP_MIN_STEPS = 2
TREND_STEP_MIN_DROP_PERCENT = 1.0
TREND_RESET_RISE_PERCENT = 2.0

ALERT_KIND_SUSTAINED_DROP = "sustained_drop"
ALERT_KIND_BUG_DROP = "bug_drop"


def evaluate_subscription_odds_change(
    repository: SqliteStorage,
    subscription: CompetitionSubscription,
    tracked_league: TrackedCompetition,
    match: ActiveEventRecord,
    *,
    confirmation_refreshes: int = 2,
    flap_window_minutes: int = 10,
    flap_epsilon: float = 0.01,
    fast_path_percent: float | None = None,
) -> SubscriptionOddsAlert | None:
    """Evaluate one global odds change against a specific chat baseline.

    Solo notifica caídas de cuota, en dos variantes:
    - caída sostenida: la misma selección baja en >=``SUSTAINED_DROP_MIN_STEPS``
      snapshots confirmados consecutivos y la caída acumulada supera el umbral
      del chat. Un rebote (suba >=``TREND_RESET_RISE_PERCENT``%) resetea la racha.
    - posible bug: una caída brusca de >=``fast_path_percent``% en un solo paso.

    Las subas y los reprices únicos por debajo de ese umbral actualizan el estado
    y el digest de cambios pequeños pero nunca notifican.

    ``fast_path_percent``: si un cambio supera este % (en puntos porcentuales) y no
    está flapeando, se confirma en el PRIMER sighting en vez de esperar
    ``confirmation_refreshes`` ciclos. Además actúa como umbral de "caída brusca"
    para la alerta de posible bug. ``None`` desactiva ambas cosas.
    """

    baseline = repository.get_event_baseline(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
    )

    if baseline is None:
        repository.initialize_event_baselines(
            subscription.telegram_chat_id,
            tracked_league.id,
            [match],
        )
        return None

    baseline_payload, tracking_meta = _split_tracking_payload(
        _loads_optional_json_dict(baseline.baseline_markets_json)
    )
    current_payload = _effective_current_payload(match)
    change_details = compute_market_change_details(baseline, match)
    max_percent_change = change_details[0].percent_change if change_details else None
    stable_snapshot_hash = _build_snapshot_hash(
        baseline_payload,
        scheduled_at=match.kickoff_at,
        raw_payload_json=match.raw_payload_json,
        epsilon=flap_epsilon,
    )
    current_snapshot_hash = _build_snapshot_hash(
        current_payload,
        scheduled_at=match.kickoff_at,
        raw_payload_json=match.raw_payload_json,
        epsilon=flap_epsilon,
    )
    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()

    if max_percent_change is None or current_snapshot_hash == stable_snapshot_hash:
        cleared_meta = _clear_pending_tracking_meta(tracking_meta)
        # Volvió al baseline: cualquier caída acumulada quedó revertida.
        cleared_meta.pop("trend", None)
        repository.upsert_event_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
            baseline_home=baseline.baseline_home,
            baseline_draw=baseline.baseline_draw,
            baseline_away=baseline.baseline_away,
            baseline_markets_json=_serialize_tracking_payload(
                baseline_payload,
                cleared_meta,
            ),
        )
        repository.resolve_small_change_with_current_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
        )
        return None

    pending_state = _normalize_pending_state(tracking_meta.get("pending"))
    is_same_pending_snapshot = pending_state.get("hash") == current_snapshot_hash
    pending_seen_count = int(pending_state.get("seen_count", 0)) + 1 if is_same_pending_snapshot else 1
    pending_first_seen_at = (
        _normalize_optional_text(pending_state.get("first_seen_at")) if is_same_pending_snapshot else now_iso
    ) or now_iso
    is_flapping = _is_recent_reversion(
        tracking_meta,
        candidate_hash=current_snapshot_hash,
        now=now,
        flap_window_minutes=flap_window_minutes,
    )
    updated_meta = {
        **_clear_pending_tracking_meta(tracking_meta),
        "pending": {
            "hash": current_snapshot_hash,
            "seen_count": pending_seen_count,
            "first_seen_at": pending_first_seen_at,
            "detected_at": now_iso,
            "flapping": is_flapping,
        },
    }

    is_big_move = (
        fast_path_percent is not None
        and max_percent_change is not None
        and max_percent_change >= fast_path_percent
    )
    fast_path = is_big_move and not is_flapping

    if pending_seen_count < max(1, confirmation_refreshes) and not fast_path:
        repository.upsert_event_baseline(
            subscription.telegram_chat_id,
            tracked_league.id,
            match.fixture_id,
            baseline_home=baseline.baseline_home,
            baseline_draw=baseline.baseline_draw,
            baseline_away=baseline.baseline_away,
            baseline_markets_json=_serialize_tracking_payload(
                baseline_payload,
                updated_meta,
            ),
        )
        return None

    trend_state = _normalize_trend_state(tracking_meta.get("trend"))
    updated_trend, alert_candidates = _apply_drop_trends(
        trend_state,
        change_details,
        bug_drop_percent=fast_path_percent,
        sustained_threshold_percent=subscription.change_percent_threshold,
    )

    should_notify = (
        subscription.notify_odds_changes
        and bool(alert_candidates)
        and not is_flapping
    )

    if should_notify:
        # Tras alertar, la caída acumulada arranca de cero para esa selección.
        for detail, _kind in alert_candidates:
            entry = updated_trend.get(_trend_key(detail))
            if entry is not None:
                entry["origin"] = entry["last"]

        confirmed_meta = _mark_confirmed_snapshot(
            tracking_meta,
            replaced_hash=stable_snapshot_hash,
            confirmed_at=now_iso,
        )
        confirmed_meta = _set_trend_meta(confirmed_meta, updated_trend)
        confirmed_payload_with_meta = _embed_tracking_meta(
            current_payload,
            confirmed_meta,
        )

        alert_details = sorted(
            (detail for detail, _kind in alert_candidates),
            key=lambda detail: (
                -detail.percent_change,
                detail.market_name,
                detail.selection,
                detail.line or "",
            ),
        )
        alert_kind = (
            ALERT_KIND_BUG_DROP
            if any(kind == ALERT_KIND_BUG_DROP for _detail, kind in alert_candidates)
            else ALERT_KIND_SUSTAINED_DROP
        )
        return SubscriptionOddsAlert(
            match=match,
            baseline=baseline,
            max_percent_change=alert_details[0].percent_change,
            change_details=tuple(alert_details),
            changed_market_types=_collect_changed_market_types(alert_details),
            confirmed_baseline_markets_payload=confirmed_payload_with_meta,
            alert_kind=alert_kind,
        )

    repository.upsert_event_baseline(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
        baseline_home=baseline.baseline_home,
        baseline_draw=baseline.baseline_draw,
        baseline_away=baseline.baseline_away,
        baseline_markets_json=_serialize_tracking_payload(
            baseline_payload,
            _set_trend_meta(updated_meta, updated_trend),
        ),
    )
    repository.upsert_small_change(
        subscription.telegram_chat_id,
        tracked_league.id,
        match.fixture_id,
        home=match.home,
        away=match.away,
        scheduled_label_date=match.kickoff_label_date,
        scheduled_label_time=match.kickoff_label_time,
        baseline_home=baseline.baseline_home,
        baseline_draw=baseline.baseline_draw,
        baseline_away=baseline.baseline_away,
        current_home=match.odds_home,
        current_draw=match.odds_draw,
        current_away=match.odds_away,
        max_percent_change=max_percent_change,
    )
    return None


def compute_max_percent_change(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> float | None:
    """Return the maximum valid percent change between baseline and current odds."""

    details = compute_market_change_details(baseline, match)
    if not details:
        return None

    return details[0].percent_change


def compute_market_change_details(
    baseline: EventBaseline,
    match: ActiveEventRecord,
) -> list[MarketChangeDetail]:
    """Return sorted market change details for every comparable odds entry."""

    baseline_entries = _flatten_market_payload(_effective_baseline_payload(baseline))
    current_entries = _flatten_market_payload(_effective_current_payload(match))

    details: list[MarketChangeDetail] = []

    for entry_key in sorted(set(baseline_entries) & set(current_entries)):
        previous_entry = baseline_entries[entry_key]
        current_entry = current_entries[entry_key]
        before = previous_entry["odds"]
        after = current_entry["odds"]
        percent_change = compute_percent_change(before, after)

        if percent_change is None or percent_change <= 0:
            continue

        details.append(
            MarketChangeDetail(
                market_type=str(current_entry["market_type"]),
                market_name=str(current_entry["market_name"]),
                selection=str(current_entry["selection"]),
                line=_normalize_optional_text(current_entry.get("line")),
                before=before,
                after=after,
                percent_change=percent_change,
            )
        )

    details.sort(
        key=lambda detail: (
            -detail.percent_change,
            detail.market_name,
            detail.selection,
            detail.line or "",
        )
    )
    return details


def compute_percent_change(
    baseline_value: float | None,
    current_value: float | None,
) -> float | None:
    """Compute absolute percent change for one odds selection."""

    if baseline_value is None or current_value is None:
        return None

    if baseline_value <= 0:
        return None

    return abs(current_value - baseline_value) / baseline_value * 100


def select_due_reminders(matches: Sequence[ActiveEventRecord]) -> list[ActiveEventRecord]:
    """Return matches that should trigger the 5-minute reminder now."""

    now = datetime.now(timezone.utc)
    due_matches: list[ActiveEventRecord] = []

    for match in matches:
        if match.alerted:
            continue

        time_label = (match.kickoff_label_time or "").strip()
        if not time_label:
            continue

        kickoff = parse_match_kickoff(match)
        if kickoff is None:
            continue

        reminder_time = kickoff - timedelta(minutes=5)
        if reminder_time <= now <= kickoff:
            due_matches.append(match)

    return due_matches


def parse_match_kickoff(match: ActiveEventRecord) -> datetime | None:
    """Parse the stored kickoff timestamp into an aware UTC datetime."""

    if match.kickoff_at is None:
        return None

    try:
        kickoff = datetime.fromisoformat(match.kickoff_at)
    except ValueError:
        return None

    if kickoff.tzinfo is None:
        kickoff = kickoff.replace(tzinfo=timezone.utc)

    return kickoff.astimezone(timezone.utc)


def market_type_display_name(market_type: str) -> str:
    """Return a friendly label for one normalized market type."""

    normalized_market_type = market_type.strip().lower()
    return MARKET_TYPE_LABELS.get(normalized_market_type, normalized_market_type.replace("_", " ").title())


def _collect_changed_market_types(
    change_details: Sequence[MarketChangeDetail],
) -> tuple[str, ...]:
    ordered: list[str] = []
    seen: set[str] = set()

    for detail in change_details:
        if detail.market_type in seen:
            continue
        seen.add(detail.market_type)
        ordered.append(detail.market_type)

    return tuple(ordered)


def _effective_baseline_payload(baseline: EventBaseline) -> dict[str, Any]:
    payload, _ = _split_tracking_payload(_loads_optional_json_dict(baseline.baseline_markets_json))
    return _merge_1x2_payload(
        payload,
        home=baseline.baseline_home,
        draw=baseline.baseline_draw,
        away=baseline.baseline_away,
    )


def _effective_current_payload(match: ActiveEventRecord) -> dict[str, Any]:
    payload, _ = _split_tracking_payload(_loads_optional_json_dict(match.markets_json))
    return _merge_1x2_payload(
        payload,
        home=match.odds_home,
        draw=match.odds_draw,
        away=match.odds_away,
    )


def _merge_1x2_payload(
    payload: dict[str, Any],
    *,
    home: float | None,
    draw: float | None,
    away: float | None,
) -> dict[str, Any]:
    merged_payload = json.loads(json.dumps(payload or {}))

    if home is None and draw is None and away is None:
        return merged_payload

    merged_payload["1x2"] = {
        "home": home,
        "draw": draw,
        "away": away,
    }
    return merged_payload


def _parse_line_float(line_str: str | None) -> float | None:
    if line_str is None:
        return None
    try:
        cleaned = str(line_str).replace("+", "").replace(",", ".").strip()
        for sep in (",", "/", "-"):
            if sep in cleaned:
                parts = [float(p.strip()) for p in cleaned.split(sep) if p.strip()]
                if parts:
                    return abs(sum(parts) / len(parts))
        return abs(float(cleaned))
    except ValueError:
        return None


def find_main_line_selections(selections: list[dict[str, Any]], is_handicap: bool = False) -> list[dict[str, Any]]:
    if not selections:
        return []

    groups = {}
    for sel in selections:
        line_str = sel.get("line")
        if line_str is None:
            continue
        val = _parse_line_float(line_str)
        if val is None:
            continue
        groups.setdefault(val, []).append(sel)

    if not groups:
        return []

    best_key = None
    best_score = float("inf")

    for key, group_sels in groups.items():
        count_penalty = 0.0 if len(group_sels) == 2 else 1000.0
        odds_diff = 0.0
        for sel in group_sels:
            odds = sel.get("odds")
            if odds is not None:
                odds_diff += abs(float(odds) - 1.95)
            else:
                odds_diff += 10.0

        score = count_penalty + odds_diff
        if score < best_score:
            best_score = score
            best_key = key

    if best_key is not None:
        return groups[best_key]
    return []


def _filter_payload_to_main_lines(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {}

    filtered = {}
    if "1x2" in payload:
        filtered["1x2"] = payload["1x2"]

    ah = payload.get("asian_handicap")
    if isinstance(ah, dict):
        selections = ah.get("selections") or []
        main_selections = find_main_line_selections(selections, is_handicap=True)
        filtered["asian_handicap"] = {
            **ah,
            "selections": main_selections
        }

    gl = payload.get("goal_line")
    if isinstance(gl, dict):
        selections = gl.get("selections") or []
        main_selections = find_main_line_selections(selections, is_handicap=False)
        filtered["goal_line"] = {
            **gl,
            "selections": main_selections
        }

    # We completely ignore alternative_markets

    return filtered


def _flatten_market_payload(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    flattened: dict[str, dict[str, Any]] = {}

    one_x_two = payload.get("1x2")
    if isinstance(one_x_two, dict):
        for selection_key, selection_label in (("home", "1"), ("draw", "X"), ("away", "2")):
            odds_value = _coerce_float(one_x_two.get(selection_key))
            if odds_value is None:
                continue
            flattened[f"1x2|{selection_key}"] = {
                "market_type": "1x2",
                "market_name": "1X2",
                "selection": selection_label,
                "line": None,
                "odds": odds_value,
            }

    for market_type in ("asian_handicap", "goal_line"):
        market_payload = payload.get(market_type)
        if isinstance(market_payload, dict):
            selections = market_payload.get("selections") or []
            is_handicap = (market_type == "asian_handicap")
            main_selections = find_main_line_selections(selections, is_handicap=is_handicap)
            temp_market_payload = dict(market_payload)
            temp_market_payload["selections"] = main_selections
            _flatten_market_object(flattened, market_type, temp_market_payload)

    # We completely ignore alternative_markets

    return flattened


def _flatten_market_object(
    flattened: dict[str, dict[str, Any]],
    market_type: str,
    market_payload: dict[str, Any],
) -> None:
    market_id = _normalize_optional_text(market_payload.get("market_id"))
    market_name = _normalize_optional_text(market_payload.get("market_name")) or market_type_display_name(
        market_type
    )

    for selection_payload in market_payload.get("selections") or []:
        if not isinstance(selection_payload, dict):
            continue

        odds_value = _coerce_float(selection_payload.get("odds"))
        if odds_value is None:
            continue

        selection = _normalize_optional_text(selection_payload.get("selection")) or "?"
        line = _normalize_optional_text(selection_payload.get("line"))
        entry_key = "|".join(
            [
                market_type,
                market_id or market_name,
                selection,
                line or "",
            ]
        )
        flattened[entry_key] = {
            "market_type": market_type,
            "market_name": market_name,
            "selection": selection,
            "line": line,
            "odds": odds_value,
        }


def _split_tracking_payload(
    payload: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}, {}

    normalized_payload = json.loads(json.dumps(payload))
    raw_meta = normalized_payload.pop(TRACKING_META_KEY, None)
    return normalized_payload, raw_meta if isinstance(raw_meta, dict) else {}


def _embed_tracking_meta(
    payload: dict[str, Any] | None,
    tracking_meta: dict[str, Any],
) -> dict[str, Any]:
    normalized_payload = json.loads(json.dumps(payload or {}))
    cleaned_meta = _prune_tracking_meta(tracking_meta)
    if cleaned_meta:
        normalized_payload[TRACKING_META_KEY] = cleaned_meta
    else:
        normalized_payload.pop(TRACKING_META_KEY, None)
    return normalized_payload


def _serialize_tracking_payload(
    payload: dict[str, Any] | None,
    tracking_meta: dict[str, Any],
) -> str | None:
    merged_payload = _embed_tracking_meta(payload, tracking_meta)
    if not merged_payload:
        return None
    return json.dumps(merged_payload, ensure_ascii=False, sort_keys=True)


def _prune_tracking_meta(tracking_meta: dict[str, Any]) -> dict[str, Any]:
    normalized_meta = dict(tracking_meta or {})
    if "pending" in normalized_meta and not normalized_meta["pending"]:
        normalized_meta.pop("pending", None)
    recent_hashes = normalized_meta.get("recent_hashes")
    if not recent_hashes:
        normalized_meta.pop("recent_hashes", None)
    if not normalized_meta.get("trend"):
        normalized_meta.pop("trend", None)
    return normalized_meta


def _trend_key(detail: MarketChangeDetail) -> str:
    return "|".join(
        [
            detail.market_type,
            detail.market_name,
            detail.selection,
            detail.line or "",
        ]
    )


def _normalize_trend_state(raw_trend: object) -> dict[str, dict[str, Any]]:
    if not isinstance(raw_trend, dict):
        return {}

    normalized: dict[str, dict[str, Any]] = {}
    for key, entry in raw_trend.items():
        if not isinstance(entry, dict):
            continue
        origin = _coerce_float(entry.get("origin"))
        last = _coerce_float(entry.get("last"))
        drops = int(entry.get("drops", 0) or 0)
        if origin is None or last is None or origin <= 0 or drops <= 0:
            continue
        normalized[str(key)] = {"origin": origin, "last": last, "drops": drops}
    return normalized


def _set_trend_meta(
    tracking_meta: dict[str, Any],
    trend_state: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    normalized_meta = dict(tracking_meta or {})
    if trend_state:
        normalized_meta["trend"] = trend_state
    else:
        normalized_meta.pop("trend", None)
    return normalized_meta


def _apply_drop_trends(
    trend_state: dict[str, dict[str, Any]],
    change_details: Sequence[MarketChangeDetail],
    *,
    bug_drop_percent: float | None,
    sustained_threshold_percent: float,
) -> tuple[dict[str, dict[str, Any]], list[tuple[MarketChangeDetail, str]]]:
    """Update per-selection drop streaks with one confirmed snapshot.

    ``change_details`` compara baseline vs actual; el paso real de esta selección
    se mide contra el último valor confirmado (``last``), no contra el baseline,
    para poder contar caídas consecutivas sin duplicar snapshots repetidos.
    Devuelve el estado actualizado y las selecciones que ameritan alerta, cada
    una con su detalle reescrito (before=origen, percent=caída acumulada para
    sostenidas; before=valor previo para caídas bruscas).
    """

    updated_trend = {key: dict(entry) for key, entry in trend_state.items()}
    alert_candidates: list[tuple[MarketChangeDetail, str]] = []

    for detail in change_details:
        key = _trend_key(detail)
        previous = updated_trend.get(key)
        previous_odds = float(previous["last"]) if previous else detail.before
        if previous_odds <= 0:
            continue

        step_percent = (previous_odds - detail.after) / previous_odds * 100

        if step_percent >= TREND_STEP_MIN_DROP_PERCENT:
            origin = float(previous["origin"]) if previous else previous_odds
            drops = int(previous["drops"]) + 1 if previous else 1
            updated_trend[key] = {"origin": origin, "last": detail.after, "drops": drops}

            if bug_drop_percent is not None and step_percent >= bug_drop_percent:
                alert_candidates.append(
                    (
                        replace(detail, before=previous_odds, percent_change=step_percent),
                        ALERT_KIND_BUG_DROP,
                    )
                )
                continue

            cumulative_percent = (origin - detail.after) / origin * 100
            if drops >= SUSTAINED_DROP_MIN_STEPS and cumulative_percent >= sustained_threshold_percent:
                alert_candidates.append(
                    (
                        replace(detail, before=origin, percent_change=cumulative_percent),
                        ALERT_KIND_SUSTAINED_DROP,
                    )
                )
        elif step_percent <= -TREND_RESET_RISE_PERCENT:
            # Rebote: si vuelve a subir, la corrección no era tal y la racha muere.
            updated_trend.pop(key, None)
        elif previous is not None:
            previous["last"] = detail.after

    return updated_trend, alert_candidates


def _clear_pending_tracking_meta(tracking_meta: dict[str, Any]) -> dict[str, Any]:
    normalized_meta = dict(tracking_meta or {})
    normalized_meta.pop("pending", None)
    return normalized_meta


def _normalize_pending_state(raw_pending: object) -> dict[str, Any]:
    if not isinstance(raw_pending, dict):
        return {}
    return {
        "hash": _normalize_optional_text(raw_pending.get("hash")),
        "seen_count": int(raw_pending.get("seen_count", 0) or 0),
        "first_seen_at": _normalize_optional_text(raw_pending.get("first_seen_at")),
        "detected_at": _normalize_optional_text(raw_pending.get("detected_at")),
        "flapping": bool(raw_pending.get("flapping")),
    }


def _mark_confirmed_snapshot(
    tracking_meta: dict[str, Any],
    *,
    replaced_hash: str,
    confirmed_at: str,
) -> dict[str, Any]:
    normalized_meta = _clear_pending_tracking_meta(tracking_meta)
    if not replaced_hash:
        return normalized_meta

    recent_hashes: list[dict[str, str]] = []
    for entry in tracking_meta.get("recent_hashes") or []:
        if not isinstance(entry, dict):
            continue
        entry_hash = _normalize_optional_text(entry.get("hash"))
        entry_at = _normalize_optional_text(entry.get("at"))
        if not entry_hash or not entry_at or entry_hash == replaced_hash:
            continue
        recent_hashes.append({"hash": entry_hash, "at": entry_at})

    recent_hashes.insert(0, {"hash": replaced_hash, "at": confirmed_at})
    normalized_meta["recent_hashes"] = recent_hashes[:RECENT_SNAPSHOT_HISTORY_SIZE]
    return normalized_meta


def _is_recent_reversion(
    tracking_meta: dict[str, Any],
    *,
    candidate_hash: str,
    now: datetime,
    flap_window_minutes: int,
) -> bool:
    if not candidate_hash:
        return False

    window = timedelta(minutes=max(1, flap_window_minutes))
    for entry in tracking_meta.get("recent_hashes") or []:
        if not isinstance(entry, dict):
            continue
        entry_hash = _normalize_optional_text(entry.get("hash"))
        entry_at = _normalize_optional_text(entry.get("at"))
        if entry_hash != candidate_hash or not entry_at:
            continue
        try:
            parsed_at = datetime.fromisoformat(entry_at)
        except ValueError:
            continue
        if parsed_at.tzinfo is None:
            parsed_at = parsed_at.replace(tzinfo=timezone.utc)
        if now - parsed_at <= window:
            return True
    return False


def _build_snapshot_hash(
    payload: dict[str, Any] | None,
    *,
    scheduled_at: str | None,
    raw_payload_json: str | None,
    epsilon: float,
) -> str:
    filtered = _filter_payload_to_main_lines(payload)
    canonical_payload = _canonicalize_for_hash(filtered, epsilon=epsilon)
    extractor_mode = _extract_snapshot_mode(raw_payload_json)
    canonical_snapshot = {
        "scheduled_at": _normalize_optional_text(scheduled_at),
        "extractor_mode": extractor_mode,
        "markets": canonical_payload,
    }
    encoded = json.dumps(canonical_snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _canonicalize_for_hash(value: Any, *, epsilon: float) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _canonicalize_for_hash(nested_value, epsilon=epsilon)
            for key, nested_value in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key) != TRACKING_META_KEY
        }
    if isinstance(value, list):
        return [_canonicalize_for_hash(item, epsilon=epsilon) for item in value]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int, float)):
        return _round_with_epsilon(float(value), epsilon)
    if isinstance(value, str):
        maybe_float = _coerce_float(value)
        if maybe_float is not None:
            return _round_with_epsilon(maybe_float, epsilon)
        return value.strip()
    return str(value)


def _round_with_epsilon(value: float, epsilon: float) -> float:
    normalized_epsilon = epsilon if epsilon > 0 else 0.01
    rounded = round(round(value / normalized_epsilon) * normalized_epsilon, 6)
    return 0.0 if abs(rounded) < normalized_epsilon else rounded


def _extract_snapshot_mode(raw_payload_json: str | None) -> str:
    payload = _loads_optional_json_dict(raw_payload_json) or {}
    if payload.get("degraded"):
        return "degraded"
    return "primary"


def _loads_optional_json_dict(raw_value: str | None) -> dict[str, Any] | None:
    normalized_value = (raw_value or "").strip()
    if not normalized_value:
        return None

    try:
        payload = json.loads(normalized_value)
    except json.JSONDecodeError:
        return None

    return payload if isinstance(payload, dict) else None


def _coerce_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        normalized_value = value.strip()
        if not normalized_value:
            return None
        try:
            return float(normalized_value)
        except ValueError:
            return None
    return None


def _normalize_optional_text(value: object) -> str | None:
    normalized_value = str(value).strip() if value is not None else ""
    return normalized_value or None


__all__ = [
    "compute_market_change_details",
    "compute_max_percent_change",
    "compute_percent_change",
    "evaluate_subscription_odds_change",
    "market_type_display_name",
    "parse_match_kickoff",
    "select_due_reminders",
]
