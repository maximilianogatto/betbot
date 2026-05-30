"""Provider hardening helpers for Sportradar HTTP.

This module turns real pipeline outputs into validation evidence. It does not
add endpoints and does not fetch network data. The CLI supplies navigation,
snapshot, features and intelligence documents; this module scores whether the
provider output is stable enough for future BetBot integration.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{2}\b")


@dataclass(frozen=True, slots=True)
class ValidationTarget:
    """One tournament validation target.

    Args:
        tournament_id: URL-facing Statshub tournament id.
        label: Human-readable label used in reports.
        category: Expected coverage class such as `top`, `women`, `minor`.
    """

    tournament_id: int
    label: str
    category: str = "unspecified"


def parse_validation_target(raw: str) -> ValidationTarget:
    """Parse `id[:label[:category]]` CLI input."""

    parts = [part.strip() for part in raw.split(":", 2)]
    if not parts or not parts[0]:
        raise ValueError(f"Invalid target: {raw!r}")
    tournament_id = int(parts[0])
    label = parts[1] if len(parts) > 1 and parts[1] else f"tournament_{tournament_id}"
    category = parts[2] if len(parts) > 2 and parts[2] else "unspecified"
    return ValidationTarget(tournament_id=tournament_id, label=label, category=category)


def build_validation_result(
    *,
    target: ValidationTarget,
    navigation: dict[str, Any],
    selected_fixture: dict[str, Any] | None,
    snapshot: dict[str, Any] | None,
    intelligence: dict[str, Any] | None,
    fixture_market_odds: dict[str, Any] | None = None,
    package_path: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build a compact validation result for one target."""

    resolved = navigation.get("resolved_tournament") if isinstance(navigation.get("resolved_tournament"), dict) else {}
    primary = resolved.get("primary") if isinstance(resolved.get("primary"), dict) else {}
    feature_quality = snapshot.get("feature_quality") if isinstance(snapshot, dict) and isinstance(snapshot.get("feature_quality"), dict) else {}
    odds = snapshot.get("odds") if isinstance(snapshot, dict) and isinstance(snapshot.get("odds"), dict) else {}
    markets = odds.get("markets") if isinstance(odds.get("markets"), dict) else {}
    fixture_markets = (
        fixture_market_odds.get("markets")
        if isinstance(fixture_market_odds, dict) and isinstance(fixture_market_odds.get("markets"), dict)
        else {}
    )
    match_markets_priced = _has_priced_markets(markets)
    fixture_markets_priced = _has_priced_markets(fixture_markets)
    provider_markets = markets if match_markets_priced or not fixture_markets_priced else fixture_markets
    provider_odds_source = odds.get("source") if match_markets_priced else (fixture_market_odds or {}).get("source")
    live_state = snapshot.get("live_state") if isinstance(snapshot, dict) and isinstance(snapshot.get("live_state"), dict) else {}
    live_delta = snapshot.get("live_delta") if isinstance(snapshot, dict) and isinstance(snapshot.get("live_delta"), dict) else {}
    live_situation = snapshot.get("live_situation") if isinstance(snapshot, dict) and isinstance(snapshot.get("live_situation"), dict) else {}
    report_summary = intelligence.get("report_summary") if isinstance(intelligence, dict) else ""
    result = {
        "target": {
            "tournament_id": target.tournament_id,
            "label": target.label,
            "category": target.category,
        },
        "resolved": {
            "found": bool(resolved.get("found")),
            "country": primary.get("country_name"),
            "name": primary.get("name"),
            "season_id": resolved.get("season_id"),
            "match_kind": resolved.get("match_kind"),
            "fixture_count": navigation.get("fixture_count"),
        },
        "selected_fixture": _compact_fixture(selected_fixture),
        "quality": {
            "has_metadata": bool(feature_quality.get("has_metadata")),
            "has_priced_odds": match_markets_priced or fixture_markets_priced,
            "has_match_markets_priced_odds": match_markets_priced,
            "has_fixture_markets_priced_odds": fixture_markets_priced,
            "has_odds_endpoint": bool(feature_quality.get("has_odds_endpoint")),
            "has_table": bool(feature_quality.get("has_table")),
            "has_team_form": bool(feature_quality.get("has_team_form")),
            "has_team_scoring": bool(feature_quality.get("has_team_scoring")),
            "has_h2h": bool(feature_quality.get("has_h2h")),
            "has_live_state": bool(feature_quality.get("has_live_state")),
            "data_completeness": feature_quality.get("data_completeness"),
            "missing_important_endpoints": feature_quality.get("missing_important_endpoints") or [],
        },
        "odds": {
            "source": provider_odds_source,
            "one_x_two": bool(provider_markets.get("1x2")),
            "handicap_count": len(provider_markets.get("handicap") or []),
            "totals_count": len(provider_markets.get("totals") or []),
            "match_markets": {
                "one_x_two": bool(markets.get("1x2")),
                "handicap_count": len(markets.get("handicap") or []),
                "totals_count": len(markets.get("totals") or []),
                "raw_market_count": markets.get("raw_market_count"),
            },
            "fixture_markets": {
                "one_x_two": bool(fixture_markets.get("1x2")),
                "handicap_count": len(fixture_markets.get("handicap") or []),
                "totals_count": len(fixture_markets.get("totals") or []),
                "raw_market_count": fixture_markets.get("raw_market_count"),
                "error": (fixture_market_odds or {}).get("error") if isinstance(fixture_market_odds, dict) else None,
            },
        },
        "live": {
            "timeline_events": live_state.get("raw_event_count"),
            "delta_events": live_delta.get("raw_event_count"),
            "situation_samples": live_situation.get("raw_sample_count"),
            "status": live_state.get("status"),
        },
        "report_quality": {
            "has_report": bool(report_summary),
            "h2h_has_dates": _h2h_has_dates(intelligence or {}),
            "traceability_has_dates": _traceability_has_dates(intelligence or {}),
            "line_count": len(str(report_summary).splitlines()) if report_summary else 0,
        },
        "report_summary": report_summary,
        "warnings": [],
        "package_path": package_path,
        "error": error,
    }
    result["warnings"] = _warnings(result)
    return result


def build_validation_summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate validation results across tournaments."""

    total = len(results)
    return {
        "targets": total,
        "resolved": sum(1 for item in results if item.get("resolved", {}).get("found")),
        "with_fixtures": sum(1 for item in results if (item.get("resolved", {}).get("fixture_count") or 0) > 0),
        "with_priced_odds": sum(1 for item in results if item.get("quality", {}).get("has_priced_odds")),
        "with_h2h": sum(1 for item in results if item.get("quality", {}).get("has_h2h")),
        "with_live_state": sum(1 for item in results if item.get("quality", {}).get("has_live_state")),
        "with_dated_h2h": sum(1 for item in results if item.get("report_quality", {}).get("h2h_has_dates")),
        "failed": sum(1 for item in results if item.get("error")),
    }


def render_validation_report(results: list[dict[str, Any]]) -> str:
    """Render provider validation evidence as Markdown."""

    summary = build_validation_summary(results)
    lines = [
        "# Sportradar Provider Validation Report",
        "",
        "## Summary",
        "",
        f"- Targets: `{summary['targets']}`",
        f"- Resolved tournaments: `{summary['resolved']}`",
        f"- Targets with fixtures: `{summary['with_fixtures']}`",
        f"- Targets with priced odds: `{summary['with_priced_odds']}`",
        f"- Targets with H2H: `{summary['with_h2h']}`",
        f"- Targets with live endpoint response: `{summary['with_live_state']}`",
        f"- Targets with dated H2H evidence: `{summary['with_dated_h2h']}`",
        f"- Failed targets: `{summary['failed']}`",
        "",
        "## Matrix",
        "",
        "| Target | Category | Resolved | Fixtures | Selected match | Odds priced | Odds source | H2H dates | Traceability dates | Live events | Warnings |",
        "|---|---|---:|---:|---|---:|---|---:|---:|---:|---|",
    ]
    for item in results:
        target = item.get("target") or {}
        resolved = item.get("resolved") or {}
        selected = item.get("selected_fixture") or {}
        quality = item.get("quality") or {}
        odds = item.get("odds") or {}
        report_quality = item.get("report_quality") or {}
        live = item.get("live") or {}
        lines.append(
            "| {target} | {category} | {resolved} | {fixtures} | {match} | {odds} | {source} | {h2h_dates} | {trace_dates} | {live_events} | {warnings} |".format(
                target=f"{target.get('label')} ({target.get('tournament_id')})",
                category=target.get("category"),
                resolved="yes" if resolved.get("found") else "no",
                fixtures=resolved.get("fixture_count"),
                match=f"{selected.get('home')} vs {selected.get('away')} ({selected.get('match_id')})",
                odds="yes" if quality.get("has_priced_odds") else "no",
                source=odds.get("source") or "-",
                h2h_dates="yes" if report_quality.get("h2h_has_dates") else "no",
                trace_dates="yes" if report_quality.get("traceability_has_dates") else "no",
                live_events=live.get("timeline_events"),
                warnings=", ".join(item.get("warnings") or []) or "-",
            )
        )
    lines.extend(["", "## Details", ""])
    for item in results:
        target = item.get("target") or {}
        resolved = item.get("resolved") or {}
        selected = item.get("selected_fixture") or {}
        lines.extend(
            [
                f"### {target.get('label')} (`{target.get('tournament_id')}`)",
                "",
                f"- Category: `{target.get('category')}`",
                f"- Tournament: `{resolved.get('country')} / {resolved.get('name')}`",
                f"- Season id: `{resolved.get('season_id')}`",
                f"- Fixture count: `{resolved.get('fixture_count')}`",
                f"- Selected fixture: `{selected.get('home')} vs {selected.get('away')}`",
                f"- Match id: `{selected.get('match_id')}`",
                f"- Kickoff UTC: `{selected.get('kickoff_utc')}`",
                f"- Package: `{item.get('package_path')}`",
                f"- Error: `{item.get('error')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _compact_fixture(fixture: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(fixture, dict):
        return {}
    home = fixture.get("home") if isinstance(fixture.get("home"), dict) else {}
    away = fixture.get("away") if isinstance(fixture.get("away"), dict) else {}
    time = fixture.get("time") if isinstance(fixture.get("time"), dict) else {}
    return {
        "match_id": fixture.get("match_id"),
        "home": home.get("name"),
        "away": away.get("name"),
        "kickoff_utc": time.get("iso_utc"),
        "in_livescore": ((fixture.get("status") or {}).get("in_livescore") if isinstance(fixture.get("status"), dict) else None),
    }


def _h2h_has_dates(intelligence: dict[str, Any]) -> bool:
    h2h = intelligence.get("h2h") if isinstance(intelligence.get("h2h"), dict) else {}
    matches = h2h.get("recent_matches") if isinstance(h2h.get("recent_matches"), list) else []
    if not matches:
        return False
    return all(bool(match.get("date_display")) for match in matches[:3] if isinstance(match, dict))


def _traceability_has_dates(intelligence: dict[str, Any]) -> bool:
    traceability = intelligence.get("traceability") if isinstance(intelligence.get("traceability"), dict) else {}
    common = traceability.get("common_opponents") if isinstance(traceability.get("common_opponents"), list) else []
    if not common:
        return False
    for item in common[:3]:
        if not isinstance(item, dict):
            return False
        home = item.get("home_team_evidence") if isinstance(item.get("home_team_evidence"), dict) else {}
        away = item.get("away_team_evidence") if isinstance(item.get("away_team_evidence"), dict) else {}
        if not home.get("date_display") or not away.get("date_display"):
            return False
    return True


def _warnings(result: dict[str, Any]) -> list[str]:
    warnings = []
    if result.get("error"):
        warnings.append("failed")
    if not result.get("resolved", {}).get("found"):
        warnings.append("not_resolved")
    if not result.get("quality", {}).get("has_priced_odds"):
        warnings.append("no_priced_odds")
    if result.get("odds", {}).get("fixture_markets", {}).get("error"):
        warnings.append("fixture_markets_error")
    if not result.get("quality", {}).get("has_h2h"):
        warnings.append("no_h2h")
    if not result.get("report_quality", {}).get("h2h_has_dates"):
        warnings.append("missing_h2h_dates")
    report_summary = result.get("report_summary")
    if isinstance(report_summary, str) and report_summary and DATE_RE.search(report_summary) is None:
        warnings.append("report_has_no_dates")
    return warnings


def _has_priced_markets(markets: dict[str, Any]) -> bool:
    return bool(markets.get("1x2") or markets.get("handicap") or markets.get("totals"))
