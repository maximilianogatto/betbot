"""Libro de apuestas: cargar, enlazar al partido, liquidar y medir exposición.

Qué pasa al cargar una apuesta:

1. **Se enlaza al partido** buscando entre los resultados archivados y los
   partidos vigentes por nombre y horario. Si el usuario nombró un equipo
   (``"Darwin -2.5"``), el enlace además resuelve si es local o visitante.
2. **Se reconstruye el marcador del minuto** en que se apostó, a partir de los
   minutos de gol archivados en `match_results`. Sin eso no se puede medir
   "cómo iba el partido cuando entré", que es la dimensión que más explica el
   resultado de una apuesta en vivo.
3. **Se busca la cuota que el bot veía** en ese instante en `odds_history`,
   para contrastarla con la que se tomó.
4. **Se revisan los límites** que fijó el usuario. Sólo avisa: nunca bloquea,
   porque la decisión y la ejecución de la apuesta son de la persona.

Cuando el partido termina y queda archivado en `match_results`, la liquidación
es automática (`settle_event`), incluidas las líneas de cuarto, los mercados de
primer y segundo tiempo y la regla asiática in-play. Lo que el sistema no sabe
liquidar queda abierto para `settle_manual`: nunca se adivina un resultado.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Optional

from core.betting.models import (
    BOOKMAKER_FAMILIES,
    BOOKMAKER_FEEDS,
    INPLAY_AH_FROM_PLACEMENT,
    USD_LIKE,
    AddBetResult,
    Bet,
    BetInput,
    BetLeg,
    LegInput,
)
from core.betting.settlement import combine_ticket, settle_leg
from core.league_naming import team_name_similarity
from core.match_identity import MIN_AVERAGE_SIMILARITY, MIN_TEAM_SIMILARITY
from core.models import MatchResult
from core.odds_markets import find_market, flatten_markets

logger = logging.getLogger(__name__)

#: Ventana para buscar el partido de una apuesta alrededor del momento de carga.
MATCH_WINDOW = timedelta(hours=36)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _split_label(label: str) -> list[str]:
    import re
    parts = re.split(r"\s+(?:vs\.?|v|x|-|–)\s+", str(label).strip(), maxsplit=1, flags=re.IGNORECASE)
    return [part for part in parts if part]


def label_similarity(label: str, home: str, away: str) -> tuple[float, Optional[str]]:
    """Cuánto se parece el texto del usuario a un partido, y a qué lado apuntó.

    Con los dos equipos nombrados se exige que ambos se parezcan (los mismos
    umbrales que usa el comparador cross-plataforma). Con uno solo, el lado que
    más se parece es el equipo elegido.
    """
    parts = _split_label(label)
    if not parts:
        return 0.0, None
    if len(parts) >= 2:
        home_score = team_name_similarity(parts[0], home)
        away_score = team_name_similarity(parts[1], away)
        if min(home_score, away_score) < MIN_TEAM_SIMILARITY:
            return 0.0, None
        average = (home_score + away_score) / 2
        return (average if average >= MIN_AVERAGE_SIMILARITY else 0.0), None
    home_score = team_name_similarity(parts[0], home)
    away_score = team_name_similarity(parts[0], away)
    if max(home_score, away_score) < MIN_TEAM_SIMILARITY:
        return 0.0, None
    return (home_score, "home") if home_score >= away_score else (away_score, "away")


def score_at_minute(result: MatchResult, minute: int) -> Optional[tuple[int, int]]:
    """Marcador en un minuto dado, desde los minutos de gol archivados."""
    if not result.goal_minutes_json:
        return None
    try:
        goals = json.loads(result.goal_minutes_json)
    except (TypeError, ValueError):
        return None
    home = sum(1 for g in goals if g.get("team") == "home" and (g.get("minute") or 0) < minute)
    away = sum(1 for g in goals if g.get("team") == "away" and (g.get("minute") or 0) < minute)
    return home, away


class LedgerService:
    def __init__(self, repository: Any = None, *, clock=_now) -> None:
        if repository is None:
            from adapters.storage import get_storage
            repository = get_storage()
        self.repository = repository
        self.clock = clock

    # ------------------------------------------------------------------ #
    # Alta
    # ------------------------------------------------------------------ #
    def add_bet(self, bet_input: BetInput) -> AddBetResult:
        if not bet_input.legs:
            raise ValueError("una apuesta necesita al menos una selección")
        if bet_input.stake <= 0:
            raise ValueError("el monto apostado tiene que ser positivo")

        warnings: list[str] = []
        now = self.clock()
        paper = bet_input.mode == "paper"
        bookmaker = (bet_input.bookmaker or "").strip().lower() or None
        currency = "U" if paper else (bet_input.currency or "USD").upper()
        fx = 1.0 if paper else self._fx_rate(bet_input, currency, warnings)
        placed_at = _parse(bet_input.placed_at)

        legs = [self._resolve_leg(leg, bookmaker=bookmaker, placed_at=placed_at, now=now,
                                  chat_id=bet_input.chat_id, warnings=warnings)
                for leg in bet_input.legs]
        if placed_at is None:
            placed_at = self._estimate_placed_at(legs, bet_input.legs) or now

        odds_total = bet_input.odds_total
        if odds_total is None:
            odds_total = 1.0
            for leg in legs:
                odds_total *= leg.odds
        if not paper:
            warnings.extend(self._limit_warnings(
                legs, stake_usd=bet_input.stake * fx if fx else None))

        bet = Bet(
            created_at=_iso(now), placed_at=_iso(placed_at), source=bet_input.source,
            chat_id=bet_input.chat_id, bookmaker=bookmaker,
            bookmaker_family=BOOKMAKER_FAMILIES.get(bookmaker or ""),
            ticket_id=bet_input.ticket_id, stake=bet_input.stake, currency=currency,
            fx_to_usd=fx, stake_usd=round(bet_input.stake * fx, 4) if fx else None,
            odds_total=round(odds_total, 4), mode=bet_input.mode, scenario=bet_input.scenario,
            thesis=bet_input.thesis, tags=",".join(bet_input.tags) or None,
            notes=bet_input.notes, model_probability=bet_input.model_probability, legs=legs,
        )
        saved = self.repository.add_bet(bet)
        # Cargada después del partido: si el resultado ya está archivado, se
        # liquida ahora (el cierre del partido ya pasó y no vuelve).
        settled = self._try_settle(saved)
        return AddBetResult(bet=settled or saved, warnings=warnings)

    def _fx_rate(self, bet_input: BetInput, currency: str, warnings: list[str]) -> Optional[float]:
        if bet_input.fx_to_usd is not None:
            return bet_input.fx_to_usd
        if currency in USD_LIKE:
            return 1.0
        if currency == "ARS":
            rate = os.getenv("LEDGER_ARS_PER_USD", "").strip()
            if rate:
                try:
                    return 1.0 / float(rate)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        warnings.append(
            f"Sin tipo de cambio para {currency}: el monto no entra en los totales en USD "
            "hasta que se cargue (LEDGER_ARS_PER_USD en el .env, o el valor en la apuesta).")
        return None

    def _resolve_leg(self, leg: LegInput, *, bookmaker: Optional[str],
                     placed_at: Optional[datetime], now: datetime, chat_id: Optional[int],
                     warnings: list[str]) -> BetLeg:
        phase = leg.placed_phase or ("live" if leg.placed_minute is not None else "prematch")
        moment = placed_at or now
        match, team_side = self._find_match(leg, moment, chat_id=chat_id)
        if match is None:
            warnings.append(f"'{leg.match_label}' no coincide con ningún partido registrado: "
                            "queda sin contexto y hay que liquidarla a mano.")

        label_teams = _label_teams(leg) if match is None else None
        side, market_type = leg.side, leg.market_type
        if side in {None, "team"} or market_type == "team_total":
            if team_side is None and match is not None:
                team_side = self._team_side(leg, match)
            if team_side is None and label_teams is not None:
                # Sin partido enlazado pero con los dos equipos escritos ("A vs B
                # <equipo>"): el lado sale del propio texto y no se pierde el pick.
                _, team_side = label_similarity(leg.team, *label_teams)
            if team_side is None:
                # Partido no registrado: se guarda igual con el equipo en el
                # label. Sin partido no hay liquidación automática.
                side = side or "team"
            elif market_type == "team_total":
                market_type = f"team_total_{team_side}"
            else:
                side = team_side

        handicap_from = leg.handicap_from or (
            "placement" if phase == "live" and market_type == "asian_handicap"
            and bookmaker in INPLAY_AH_FROM_PLACEMENT else "full")

        placed_score = leg.placed_score
        if placed_score is None and phase == "prematch":
            placed_score = (0, 0)
        if placed_score is None and match is not None and leg.placed_minute is not None:
            placed_score = self._score_at(match, leg.placed_minute)
        if placed_score is None and handicap_from == "placement":
            warnings.append("Handicap con regla asiática in-play pero sin marcador al apostar: "
                            "no se va a poder liquidar solo.")

        resolved = BetLeg(
            platform=getattr(match, "platform", None) if match else leg.platform,
            external_event_id=(str(getattr(match, "external_event_id", "") or "") or None)
            if match else leg.external_event_id,
            match_label=leg.match_label,
            home=getattr(match, "home", None) if match else (label_teams[0] if label_teams else None),
            away=getattr(match, "away", None) if match else (label_teams[1] if label_teams else None),
            competition_name=getattr(match, "competition_name", None) if match else None,
            kickoff_at=getattr(match, "kickoff_at", None) if match else None,
            placed_phase=phase, placed_minute=leg.placed_minute,
            placed_home_score=placed_score[0] if placed_score else None,
            placed_away_score=placed_score[1] if placed_score else None,
            market_type=market_type, market_period=leg.market_period, side=side or "team",
            line=leg.line, odds=leg.odds, handicap_from=handicap_from,
        )
        # La cuota observada sólo tiene sentido si sabemos CUÁNDO se apostó:
        # con hora explícita, o en vivo con el minuto (kickoff + minuto). Una
        # apuesta pre-match sin hora se deja vacía en vez de inventar el precio
        # de un instante cualquiera; el CLV contra el cierre sí es real.
        when = placed_at or self._estimate_placed_at([resolved], [leg])
        if when is not None:
            resolved.observed_odds = self._observed_odds(resolved, bookmaker=bookmaker, at=when)
        return resolved

    def _find_match(self, leg: LegInput, moment: datetime,
                    *, chat_id: Optional[int] = None) -> tuple[Any, Optional[str]]:
        """Busca el partido entre los resultados archivados y los vigentes."""
        candidates: list[tuple[float, Any, Optional[str]]] = []
        since, until = _iso(moment - MATCH_WINDOW), _iso(moment + MATCH_WINDOW)
        try:
            archived = self.repository.list_match_results(since=since, until=until, limit=400)
        except Exception:
            logger.exception("Ledger: no se pudieron leer los resultados archivados")
            archived = []
        for result in archived:
            score, side = label_similarity(leg.team or leg.match_label, result.home, result.away)
            if score:
                candidates.append((score, result, side))
        if not candidates:
            for event in self._active_events(chat_id):
                score, side = label_similarity(leg.team or leg.match_label, event.home, event.away)
                if score:
                    candidates.append((score, event, side))
        if not candidates:
            return None, None
        candidates.sort(key=lambda item: item[0], reverse=True)
        _, match, side = candidates[0]
        return match, side

    def _active_events(self, chat_id: Optional[int]) -> list[Any]:
        """Partidos vigentes del chat. Sin chat sólo se buscan resultados archivados."""
        if chat_id is None:
            return []
        try:
            rows = self.repository.get_all_active_events_with_league(chat_id)
        except Exception:
            logger.exception("Ledger: no se pudieron leer los partidos vigentes")
            return []
        return [_active_event_view(row) for row in rows]

    @staticmethod
    def _team_side(leg: LegInput, match: Any) -> Optional[str]:
        text = leg.team or leg.match_label
        home = team_name_similarity(text, match.home)
        away = team_name_similarity(text, match.away)
        if max(home, away) < MIN_TEAM_SIMILARITY:
            return None
        return "home" if home >= away else "away"

    def _score_at(self, match: Any, minute: int) -> Optional[tuple[int, int]]:
        result = match if isinstance(match, MatchResult) else self._result_for(match)
        return score_at_minute(result, minute) if result is not None else None

    def _result_for(self, match: Any) -> Optional[MatchResult]:
        platform = getattr(match, "platform", None)
        external_id = getattr(match, "external_event_id", None)
        if not platform or not external_id:
            return None
        try:
            return self.repository.get_match_result(
                platform=platform, external_event_id=str(external_id))
        except Exception:
            logger.exception("Ledger: no se pudo leer el resultado del partido")
            return None

    def _estimate_placed_at(self, legs: list[BetLeg], inputs: list[LegInput]) -> Optional[datetime]:
        """Sin hora explícita, se estima desde el kickoff y el minuto de la apuesta."""
        for leg, original in zip(legs, inputs):
            kickoff = _parse(leg.kickoff_at)
            if kickoff and original.placed_minute is not None:
                extra = 15 if original.placed_minute > 45 else 0  # descanso
                return kickoff + timedelta(minutes=original.placed_minute + extra)
        return None

    # ------------------------------------------------------------------ #
    # Cuotas observadas y CLV
    # ------------------------------------------------------------------ #
    def _snapshot_rows(self, snapshot: Any) -> list[dict[str, Any]]:
        if snapshot is None or not snapshot.markets_json:
            return []
        try:
            markets = json.loads(snapshot.markets_json)
        except (TypeError, ValueError):
            return []
        return flatten_markets(markets, home=snapshot.home or "", away=snapshot.away or "")

    def _observed_odds(self, leg: BetLeg, *, bookmaker: Optional[str],
                       at: datetime) -> Optional[float]:
        feed = BOOKMAKER_FEEDS.get(bookmaker or "")
        if not feed or not leg.external_event_id:
            return None
        try:
            series = self.repository.list_snapshots(
                platform=feed, external_event_id=leg.external_event_id)
        except Exception:
            return None
        target = _iso(at)
        previous = [s for s in series if (s.captured_at or "") <= target and not s.is_suspended]
        row = find_market(self._snapshot_rows(previous[-1] if previous else None),
                          market_type=leg.market_type, market_period=leg.market_period,
                          side=leg.side, line=leg.line)
        return row["odds"] if row else None

    def _closing(self, leg: BetLeg, bookmaker: Optional[str]) -> tuple[Optional[float], Optional[float]]:
        """(cuota de cierre de esa línea, línea vigente al cierre)."""
        feed = BOOKMAKER_FEEDS.get(bookmaker or "")
        if not feed or not leg.external_event_id:
            return None, None
        try:
            if leg.placed_phase == "prematch" and leg.kickoff_at:
                snapshot = self.repository.last_prematch_snapshot(
                    platform=feed, external_event_id=leg.external_event_id,
                    kickoff_at=leg.kickoff_at)
            else:
                snapshot = self.repository.last_snapshot(
                    platform=feed, external_event_id=leg.external_event_id)
        except Exception:
            return None, None
        rows = self._snapshot_rows(snapshot)
        exact = find_market(rows, market_type=leg.market_type, market_period=leg.market_period,
                            side=leg.side, line=leg.line)
        if exact:
            return exact["odds"], leg.line
        same_side = [r for r in rows if r["market_type"] == leg.market_type
                     and r["market_period"] == leg.market_period and r["side"] == leg.side]
        # La línea que tomamos ya no se ofrecía: se informa cuál quedó vigente,
        # que es cuánto se movió el mercado desde que entramos.
        return (None, same_side[0]["line"]) if same_side else (None, None)

    # ------------------------------------------------------------------ #
    # Liquidación
    # ------------------------------------------------------------------ #
    def settle_event(self, *, platform: str, external_event_id: str) -> int:
        """Liquida las apuestas abiertas de un partido que ya terminó."""
        settled = 0
        for bet in self.repository.bets_for_event(
                platform=platform, external_event_id=str(external_event_id), only_open=True):
            if self._try_settle(bet) is not None:
                settled += 1
        return settled

    def settle_pending(self) -> int:
        return sum(1 for bet in self.repository.list_open_bets() if self._try_settle(bet))

    def _try_settle(self, bet: Bet) -> Optional[Bet]:
        """Liquida si TODAS las patas tienen resultado. None si falta algo."""
        results = []
        for leg in bet.legs:
            if not leg.platform or not leg.external_event_id:
                return None
            result = self.repository.get_match_result(
                platform=leg.platform, external_event_id=leg.external_event_id)
            if result is None or result.final_home_score is None:
                return None
            if (result.status or "").upper() != "FINISHED":
                return None  # suspendido o postergado: lo liquida una persona
            halftime = ((result.ht_home_score, result.ht_away_score)
                        if result.ht_home_score is not None else None)
            placement = ((leg.placed_home_score, leg.placed_away_score)
                         if leg.placed_home_score is not None else None)
            outcome = settle_leg(
                market_type=leg.market_type, market_period=leg.market_period, side=leg.side,
                line=leg.line, odds=leg.odds,
                final=(result.final_home_score, result.final_away_score),
                halftime=halftime, placement=placement, handicap_from=leg.handicap_from)
            if outcome is None:
                return None  # mercado que no sabemos liquidar: queda a mano
            results.append((leg, outcome))

        status, factor = combine_ticket([outcome for _, outcome in results])
        if status == "won" and len(results) > 1:
            # En combinadas la cuota del ticket manda: la casa redondea el producto.
            factor = bet.odds_total
        for leg, outcome in results:
            leg.status, leg.payout_factor = outcome.status, outcome.payout_factor
            leg.closing_odds, leg.closing_line = self._closing(leg, bet.bookmaker)
            leg.clv = (round(leg.odds / leg.closing_odds - 1, 4)
                       if leg.closing_odds and leg.closing_line == leg.line else None)
        return_amount = bet.stake * factor
        profit = return_amount - bet.stake
        return self.repository.settle_bet(
            bet.id, status=status, return_amount=return_amount, profit=profit,
            profit_usd=profit * bet.fx_to_usd if bet.fx_to_usd else None,
            settlement_source="auto", legs=[leg for leg, _ in results])

    def settle_manual(self, bet_id: int, status: str, *, return_amount: float | None = None,
                      note: str | None = None) -> Bet:
        """Liquidación a mano: mercados que no sabemos liquidar, cashout, anulación de la casa."""
        valid = {"won", "lost", "half_won", "half_lost", "push", "void", "cashout"}
        if status not in valid:
            raise ValueError(f"estado inválido: {status}. Opciones: {', '.join(sorted(valid))}")
        bet = self.repository.get_bet(bet_id)
        if bet is None:
            raise ValueError(f"no existe la apuesta #{bet_id}")
        if return_amount is None:
            factor = {"won": bet.odds_total, "lost": 0.0, "push": 1.0, "void": 1.0,
                      "half_won": (bet.odds_total + 1) / 2, "half_lost": 0.5}.get(status)
            if factor is None:
                raise ValueError("un cashout necesita el monto cobrado")
            return_amount = bet.stake * factor
        profit = return_amount - bet.stake
        return self.repository.settle_bet(
            bet_id, status=status, return_amount=return_amount, profit=profit,
            profit_usd=profit * bet.fx_to_usd if bet.fx_to_usd else None,
            settlement_source="manual", legs=[], notes=note)

    def void_bet(self, bet_id: int, reason: str = "anulada por el usuario") -> Bet:
        """Anula sin borrar: la fila queda, fuera de los reportes."""
        return self.settle_manual(bet_id, "void", note=reason)

    # ------------------------------------------------------------------ #
    # Riesgo
    # ------------------------------------------------------------------ #
    def exposure(self) -> dict[str, Any]:
        """Qué hay en juego ahora, por partido y por escenario, y cómo va el día."""
        open_bets = self.repository.list_open_bets(mode="real")
        by_match: dict[str, dict[str, Any]] = {}
        by_scenario: dict[str, float] = {}
        for bet in open_bets:
            stake = bet.stake_usd or 0.0
            labels = {f"{leg.home} vs {leg.away}" if leg.home else leg.match_label
                      for leg in bet.legs}
            for label in labels:
                entry = by_match.setdefault(label, {"stake_usd": 0.0, "bets": 0})
                entry["stake_usd"] += stake
                entry["bets"] += 1
            if bet.scenario:
                by_scenario[bet.scenario] = by_scenario.get(bet.scenario, 0.0) + stake
        today = self.clock().astimezone(timezone.utc).date().isoformat()
        pnl, settled = self.repository.settled_pnl_since(since=today)
        return {
            "open_bets": len(open_bets),
            "open_stake_usd": round(sum(bet.stake_usd or 0.0 for bet in open_bets), 2),
            "by_match": {k: {"stake_usd": round(v["stake_usd"], 2), "bets": v["bets"]}
                         for k, v in sorted(by_match.items(), key=lambda kv: -kv[1]["stake_usd"])},
            "by_scenario": {k: round(v, 2) for k, v in by_scenario.items()},
            "today_pnl_usd": round(pnl, 2),
            "today_settled": settled,
            "limits": self.repository.get_limits(),
        }

    def set_limit(self, key: str, value: float | None) -> None:
        self.repository.set_limit(key, value)

    def _limit_warnings(self, legs: list[BetLeg], *, stake_usd: Optional[float]) -> list[str]:
        limits = self.repository.get_limits()
        if stake_usd is None or not any(value is not None for value in limits.values()):
            return []
        warnings: list[str] = []
        current = self.exposure()
        if limits["max_stake_per_bet_usd"] and stake_usd > limits["max_stake_per_bet_usd"]:
            warnings.append(f"⚠️ Monto {stake_usd:.2f} USD supera tu máximo por apuesta "
                            f"({limits['max_stake_per_bet_usd']:.2f}).")
        if limits["max_open_exposure_usd"] and \
                current["open_stake_usd"] + stake_usd > limits["max_open_exposure_usd"]:
            warnings.append(f"⚠️ La exposición abierta quedaría en "
                            f"{current['open_stake_usd'] + stake_usd:.2f} USD "
                            f"(tu límite: {limits['max_open_exposure_usd']:.2f}).")
        if limits["daily_stop_loss_usd"] and \
                current["today_pnl_usd"] <= -abs(limits["daily_stop_loss_usd"]):
            warnings.append(f"⚠️ Hoy vas {current['today_pnl_usd']:.2f} USD: alcanzaste tu "
                            f"stop-loss diario ({-abs(limits['daily_stop_loss_usd']):.2f}).")
        for leg in legs:
            label = f"{leg.home} vs {leg.away}" if leg.home else leg.match_label
            match_exposure = current["by_match"].get(label, {"stake_usd": 0.0, "bets": 0})
            if limits["max_exposure_per_match_usd"] and \
                    match_exposure["stake_usd"] + stake_usd > limits["max_exposure_per_match_usd"]:
                warnings.append(
                    f"⚠️ {label}: quedarían {match_exposure['stake_usd'] + stake_usd:.2f} USD "
                    f"en juego (tu límite por partido: {limits['max_exposure_per_match_usd']:.2f}). "
                    "Varias apuestas al mismo partido dependen del mismo escenario.")
            if limits["max_bets_per_match"] and \
                    match_exposure["bets"] + 1 > limits["max_bets_per_match"]:
                warnings.append(f"⚠️ {label}: sería la apuesta #{match_exposure['bets'] + 1} "
                                f"al partido (tu límite: {int(limits['max_bets_per_match'])}).")
        return warnings


def _label_teams(leg: LegInput) -> Optional[tuple[str, str]]:
    """Local y visitante escritos por el usuario cuando nombró partido *y* equipo."""
    if not leg.team or leg.team == leg.match_label:
        return None
    parts = _split_label(leg.match_label)
    return (parts[0], parts[1]) if len(parts) >= 2 else None


def _active_event_view(row: Any) -> Any:
    """Fila de ``get_all_active_events_with_league`` (dict) -> objeto con los campos
    que el ledger lee de un partido, igual que un ``MatchResult`` archivado."""
    if not isinstance(row, dict):
        return row
    return SimpleNamespace(
        platform=row.get("platform"),
        external_event_id=row.get("external_event_id"),
        home=row.get("home"),
        away=row.get("away"),
        competition_name=row.get("league_name"),
        kickoff_at=row.get("scheduled_at"),
    )
