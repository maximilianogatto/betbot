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
from zoneinfo import ZoneInfo

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
from core.match_identity import (
    MIN_AVERAGE_SIMILARITY, MIN_TEAM_SIMILARITY, age_groups, category_compatible,
)
from core.models import MatchResult
from core.odds_markets import find_market, flatten_markets
from services.live_watch import halftime_states

logger = logging.getLogger(__name__)

#: Más vieja que esto, la cotización guardada no se usa para una apuesta nueva.
FX_MAX_AGE = timedelta(days=3)

#: Ventana para buscar el partido de una apuesta alrededor del momento de carga.
MATCH_WINDOW = timedelta(hours=36)
#: Enlace tardío: resultados archivados hasta 10 días después de la apuesta (una
#: pre-match se carga días antes), o poco antes si se apostó en vivo.
LATE_LINK_LOOKBACK = timedelta(days=10)
LATE_LINK_BEFORE = timedelta(hours=4)
#: Pata ya enlazada con horario: el resultado tiene que ser de ese mismo partido.
KICKOFF_TOLERANCE = timedelta(hours=3)
#: Un watch archiva el resultado hasta ~3 h después de salir en vivo.
RECORDED_AFTER_KICKOFF = timedelta(hours=10)


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
            stored = self.fx_rate("ARS")
            if stored and stored.get("fresh"):
                return 1.0 / stored["ars_per_usd"]
            rate = os.getenv("LEDGER_ARS_PER_USD", "").strip()
            if rate:
                try:
                    return 1.0 / float(rate)
                except (TypeError, ValueError, ZeroDivisionError):
                    pass
        warnings.append(
            f"Sin tipo de cambio para {currency}: el monto entra en los totales en USD cuando "
            "el bot lea la cotización de dolarhoy.com (se actualiza sola cada 30 min).")
        return None

    def fx_rate(self, currency: str = "ARS") -> Optional[dict[str, Any]]:
        """Última cotización guardada (pesos por dólar), con su antigüedad."""
        raw = self.repository.get_ledger_setting(f"fx:{currency}")
        if not raw:
            return None
        try:
            info = json.loads(raw)
        except (TypeError, ValueError):
            return None
        fetched = _parse(info.get("fetched_at"))
        info["fresh"] = fetched is not None and self.clock() - fetched <= FX_MAX_AGE
        return info

    def set_fx_rate(self, currency: str, ars_per_usd: float, **details: Any) -> int:
        """Guarda la cotización y cotiza a USD las apuestas que no tenían tipo de cambio.

        Devuelve cuántas apuestas se cotizaron con este valor (las cargadas cuando no
        había cotización, o antes de que existiera esta fuente).
        """
        if ars_per_usd <= 0:
            raise ValueError("la cotización tiene que ser positiva")
        info = {"ars_per_usd": round(float(ars_per_usd), 4), "fetched_at": _iso(self.clock()), **details}
        self.repository.set_ledger_setting(f"fx:{currency}", json.dumps(info, ensure_ascii=False))
        return self.repository.apply_fx_rate(currency, 1.0 / float(ars_per_usd))

    def _resolve_leg(self, leg: LegInput, *, bookmaker: Optional[str],
                     placed_at: Optional[datetime], now: datetime, chat_id: Optional[int],
                     warnings: list[str]) -> BetLeg:
        phase = leg.placed_phase or ("live" if leg.placed_minute is not None else "prematch")
        moment = placed_at or now
        match, team_side = self._find_match(leg, moment, chat_id=chat_id, bookmaker=bookmaker)
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

    def _find_match(self, leg: LegInput, moment: datetime, *, chat_id: Optional[int] = None,
                    bookmaker: Optional[str] = None) -> tuple[Any, Optional[str]]:
        """Busca el partido: resultados archivados, vigentes del chat y los que sigue el watch."""
        candidates: list[tuple[float, Any, Optional[str]]] = []
        since, until = _iso(moment - MATCH_WINDOW), _iso(moment + MATCH_WINDOW)
        try:
            archived = self.repository.list_match_results(since=since, until=until, limit=400)
        except Exception:
            logger.exception("Ledger: no se pudieron leer los resultados archivados")
            archived = []
        named = f"{leg.match_label} {leg.team or ''}"
        for result in archived:
            score, side = label_similarity(leg.team or leg.match_label, result.home, result.away)
            if score and category_compatible(named, _match_text(result)):
                candidates.append((score, result, side))
        if not candidates:
            for event in self._active_events(chat_id):
                score, side = label_similarity(leg.team or leg.match_label, event.home, event.away)
                if score and category_compatible(named, _match_text(event)):
                    candidates.append((score, event, side))
        if not candidates:
            for view in self._watched_events(chat_id, moment):
                score, side = label_similarity(leg.team or leg.match_label, view.home, view.away)
                if score and category_compatible(named, _match_text(view)):
                    candidates.append((score, view, side))
        if not candidates:
            return None, None
        # Con puntajes parecidos: la casa de la apuesta y, entre las del watch, una
        # que ya tiene marcador (el resultado se archiva desde una de ésas).
        own_feed = BOOKMAKER_FEEDS.get(bookmaker or "")
        _, match, side = max(candidates, key=lambda item: (
            round(item[0], 1), own_feed is not None and getattr(item[1], "platform", None) == own_feed,
            bool(getattr(item[1], "has_score", False))))
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

    def _watched_events(self, chat_id: Optional[int],
                        moment: Optional[datetime] = None) -> list[Any]:
        """Partidos que el watch del chat está siguiendo, uno por casa donde se lo vio.

        Cada casa trae su id de evento y sus nombres ("Bnot Netanya (W)" en betovo,
        "Bnot Netanya FC" en solcasino): con eso la apuesta queda enlazada aunque la
        liga no esté trackeada.
        """
        if chat_id is None:
            return []
        try:
            entries = self.repository.list_live_watches(chat_id)
        except Exception:
            logger.exception("Ledger: no se pudieron leer los partidos en vigilancia")
            return []
        views = []
        for entry in entries:
            kickoff = _parse(entry.kickoff_at)
            if moment is not None and kickoff is not None and abs(kickoff - moment) > MATCH_WINDOW:
                continue
            for platform, state in (entry.live_state or {}).items():
                if platform == "_alerts" or not isinstance(state, dict) or not state.get("event_id"):
                    continue
                views.append(SimpleNamespace(
                    platform=platform, external_event_id=str(state["event_id"]),
                    home=state.get("home") or entry.home, away=state.get("away") or entry.away,
                    competition_name=entry.league_hint, kickoff_at=entry.kickoff_at,
                    recorded_at=None, has_score=state.get("home_score") is not None))
        return views

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
        return len(self.run_settlement())

    def run_settlement(self) -> list[Bet]:
        """Enlaza tarde lo que quedó sin partido y liquida lo abierto que ya terminó.

        Lo corre un job periódico. Devuelve las apuestas que se cerraron en esta
        pasada, para avisarle a cada chat.
        """
        open_bets = self.repository.list_open_bets()
        if not open_bets:
            return []
        recent = self.repository.list_match_results_recorded_since(
            since=_iso(self.clock() - LATE_LINK_LOOKBACK), limit=500)
        recent += self._halftime_results()
        settled = []
        for bet in open_bets:
            self._link_late(bet, recent)
            done = self._try_settle(bet, recent=recent)
            if done is not None:
                settled.append(done)
        return settled

    def _link_late(self, bet: Bet, recent: list[MatchResult]) -> None:
        """Patas cargadas sin partido: se enlazan si después apareció uno que coincide.

        Primero contra los resultados archivados; si no, contra los partidos vigentes
        del chat (una liga que se empezó a trackear después de cargar la apuesta) y
        contra los que sigue el watch.
        """
        active: Optional[list[Any]] = None
        watched: Optional[list[Any]] = None
        for leg in bet.legs:
            if leg.external_event_id:
                continue
            result = self._result_by_teams(leg, bet, recent) if recent else None
            if result is None and bet.chat_id is not None:
                if active is None:
                    active = self._active_events(bet.chat_id)
                result = self._result_by_teams(leg, bet, active)
            if result is None and bet.chat_id is not None:
                if watched is None:
                    watched = self._watched_events(bet.chat_id)
                result = self._result_by_teams(leg, bet, watched)
            if result is None or not result.platform or not result.external_event_id:
                continue
            side = leg.side
            if side == "team":
                side = label_similarity(leg.match_label, result.home, result.away)[1] or side
            if self.repository.link_leg(
                    leg.id, platform=result.platform, external_event_id=str(result.external_event_id),
                    home=result.home, away=result.away, competition_name=result.competition_name,
                    kickoff_at=result.kickoff_at, side=side):
                leg.platform, leg.external_event_id = result.platform, str(result.external_event_id)
                leg.home, leg.away, leg.side = result.home, result.away, side
                leg.competition_name = result.competition_name or leg.competition_name
                leg.kickoff_at = result.kickoff_at or leg.kickoff_at
                logger.info("Ledger: pata %s de #%s enlazada tarde a %s %s", leg.id, bet.id,
                            result.platform, result.external_event_id)

    def _result_by_teams(self, leg: BetLeg, bet: Bet,
                         results: list[MatchResult]) -> Optional[MatchResult]:
        """El resultado archivado de ese partido, por equipos, categoría y fecha.

        Hace falta porque el watch archiva con el id de la casa donde lo vio en
        vivo, que no tiene por qué ser la de la apuesta.
        """
        label = f"{leg.home} vs {leg.away}" if leg.home and leg.away else leg.match_label
        named = f"{label} {leg.competition_name or ''}"
        kickoff = _parse(leg.kickoff_at)
        placed = _parse(bet.placed_at) or _parse(bet.created_at)
        own_feed = BOOKMAKER_FEEDS.get(bet.bookmaker or "")
        best, best_key = None, None
        for result in results:
            if not result.home or not result.away:
                continue
            score, _ = label_similarity(label, result.home, result.away)
            if not score or not category_compatible(named, _match_text(result)):
                continue
            result_kickoff = _parse(result.kickoff_at)
            recorded = _parse(getattr(result, "recorded_at", None))
            if kickoff is not None:
                if result_kickoff is not None:
                    if abs(result_kickoff - kickoff) > KICKOFF_TOLERANCE:
                        continue
                elif recorded is None or not kickoff <= recorded <= kickoff + RECORDED_AFTER_KICKOFF:
                    continue
                gap = abs(((result_kickoff or recorded) - kickoff).total_seconds())
            elif placed is not None:
                when = result_kickoff or recorded
                if when is None or not placed - LATE_LINK_BEFORE <= when <= placed + LATE_LINK_LOOKBACK:
                    continue
                gap = abs((when - placed).total_seconds())
            else:
                gap = 0.0
            # Con puntajes parecidos gana el evento de la propia casa de la apuesta
            # (su cuota observada y su CLV son contra esa casa), después el que nombra
            # la categoría en los equipos ("San Marino U21" antes que "San Marino") y
            # al final el más cercano en el tiempo.
            own_book = own_feed is not None and result.platform == own_feed
            same_names = age_groups(named) == age_groups(f"{result.home} {result.away}")
            key = (round(score, 1), own_book, same_names, -gap)
            if best_key is None or key > best_key:
                best, best_key = result, key
        return best

    def _halftime_results(self) -> list[MatchResult]:
        """Entretiempos que el watch ya vio, de partidos que siguen en juego.

        Con eso las apuestas del 1er tiempo se liquidan en el descanso, sin esperar
        al final. No se archivan: son resultados provisorios (status HALFTIME).
        """
        try:
            entries = self.repository.list_all_active_live_watches()
        except Exception:
            logger.exception("Ledger: no se pudieron leer los partidos en vigilancia")
            return []
        results = []
        for entry in entries:
            states = {platform: state for platform, state in (entry.live_state or {}).items()
                      if platform != "_alerts" and isinstance(state, dict) and state.get("event_id")}
            with_halftime = halftime_states(states)
            if not with_halftime:
                continue
            platform, state = with_halftime[0]
            results.append(MatchResult(
                home=state.get("home") or entry.home, away=state.get("away") or entry.away,
                status="HALFTIME", source="live_watch", recorded_at=_iso(self.clock()),
                platform=platform, external_event_id=str(state["event_id"]),
                competition_name=entry.league_hint, kickoff_at=entry.kickoff_at,
                ht_home_score=state["ht_home_score"], ht_away_score=state["ht_away_score"],
                raw_payload_json=json.dumps({"_event_ids": {
                    name: str(item["event_id"]) for name, item in states.items()}})))
        return results

    def _try_settle(self, bet: Bet, *, recent: Optional[list[MatchResult]] = None) -> Optional[Bet]:
        """Liquida si TODAS las patas tienen resultado. None si falta algo.

        Una pata del 1er tiempo alcanza con el entretiempo (aunque el partido siga);
        las demás necesitan el final.
        """
        results = []
        for leg in bet.legs:
            result = None
            if leg.platform and leg.external_event_id:
                result = self.repository.get_match_result(
                    platform=leg.platform, external_event_id=leg.external_event_id)
            if not _decides(result, leg) and recent:
                found = _result_by_alias(leg, recent) or self._result_by_teams(leg, bet, recent)
                result = found if _decides(found, leg) else result
            if not _decides(result, leg):
                return None
            halftime = ((result.ht_home_score, result.ht_away_score)
                        if result.ht_home_score is not None else None)
            final = ((result.final_home_score, result.final_away_score)
                     if result.final_home_score is not None else None)
            placement = ((leg.placed_home_score, leg.placed_away_score)
                         if leg.placed_home_score is not None else None)
            outcome = settle_leg(
                market_type=leg.market_type, market_period=leg.market_period, side=leg.side,
                line=leg.line, odds=leg.odds,
                final=final,
                halftime=halftime, placement=placement, handicap_from=leg.handicap_from)
            if outcome is None:
                return None  # mercado que no sabemos liquidar: queda a mano
            results.append((leg, outcome))

        if (any(not leg.odds for leg, _ in results)
                and not all(outcome.status in {"won", "lost"} for _, outcome in results)):
            return None  # Bet Builder con una pata devuelta/a medias: sin cuotas por pata, a mano
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

    # ------------------------------------------------------------------ #
    # Reportes
    # ------------------------------------------------------------------ #
    def report(self, since: datetime, until: datetime, *, chat_id: Optional[int] = None,
               label: str = "") -> dict[str, Any]:
        """Resumen de un período: lo cargado, lo liquidado (P&L en USD) y lo abierto.

        Lo liquidado se cuenta por fecha de liquidación. Montos sin cotización a USD
        (ARS sin tipo de cambio) van aparte, en su moneda. Los tips en papel se miden
        en unidades por fuente (#tag).
        """
        window = {"since": _iso(since), "until": _iso(until), "chat_id": chat_id}
        placed = [bet for bet in self.repository.bets_between(by="placed", **window)
                  if bet.status != "void"]
        settled = self.repository.bets_between(by="settled", **window)
        real = [bet for bet in settled if bet.mode == "real"]
        counted = [bet for bet in real if bet.status != "void"]
        in_usd = [bet for bet in counted if bet.stake_usd is not None and bet.profit_usd is not None]

        def summary(bets: list[Bet]) -> dict[str, Any]:
            staked = sum(bet.stake_usd for bet in bets)
            profit = sum(bet.profit_usd for bet in bets)
            return {"bets": len(bets), "staked_usd": round(staked, 2), "profit_usd": round(profit, 2),
                    "roi": round(profit / staked, 4) if staked else None}

        def grouped(key) -> list[dict[str, Any]]:
            groups: dict[str, list[Bet]] = {}
            for bet in in_usd:
                for name in key(bet):
                    groups.setdefault(name, []).append(bet)
            return sorted(({"name": name, **summary(bets)} for name, bets in groups.items()),
                          key=lambda item: -item["profit_usd"])

        statuses = {status: sum(1 for bet in real if bet.status == status)
                    for status in ("won", "half_won", "push", "half_lost", "lost", "void", "cashout")}
        decided = [bet for bet in counted if bet.status in {"won", "half_won", "lost", "half_lost"}]
        without_usd: dict[str, float] = {}
        for bet in counted:
            if bet.profit_usd is None and bet.profit is not None:
                without_usd[bet.currency] = round(without_usd.get(bet.currency, 0.0) + bet.profit, 2)
        placed_real = [bet for bet in placed if bet.mode == "real"]
        placed_without_usd: dict[str, float] = {}
        for bet in placed_real:
            if bet.stake_usd is None:
                placed_without_usd[bet.currency] = placed_without_usd.get(bet.currency, 0.0) + bet.stake
        open_bets = [bet for bet in self.repository.list_open_bets(mode="real")
                     if chat_id is None or bet.chat_id == chat_id]
        ranked = sorted(in_usd, key=lambda bet: bet.profit_usd)
        tips = [bet for bet in settled if bet.mode == "paper" and bet.status != "void"]
        tip_groups: dict[str, list[Bet]] = {}
        for bet in tips:
            for tag in (bet.tags or "").split(",") or [""]:
                tip_groups.setdefault(tag or "(sin fuente)", []).append(bet)
        return {
            "label": label, "since": _iso(since), "until": _iso(until), "chat_id": chat_id,
            "placed": {"bets": len(placed_real),
                       "stake_usd": round(sum(bet.stake_usd or 0.0 for bet in placed_real), 2),
                       "without_usd": {k: round(v, 2) for k, v in placed_without_usd.items()}},
            "settled": {**summary(in_usd), **statuses,
                        "hit_rate": round(sum(bet.status in {"won", "half_won"} for bet in decided)
                                          / len(decided), 4) if decided else None,
                        "without_usd": without_usd},
            "by_bookmaker": grouped(lambda bet: [bet.bookmaker or "?"]),
            "by_tag": grouped(lambda bet: [t for t in (bet.tags or "").split(",") if t] or ["(sin tag)"]),
            "by_market": grouped(lambda bet: [bet.legs[0].market_type if len(bet.legs) == 1 else "combo"]),
            "best": _bet_brief(ranked[-1]) if ranked and ranked[-1].profit_usd > 0 else None,
            "worst": _bet_brief(ranked[0]) if ranked and ranked[0].profit_usd < 0 else None,
            "open": {"bets": len(open_bets),
                     "stake_usd": round(sum(bet.stake_usd or 0.0 for bet in open_bets), 2)},
            "tips": sorted(({"source": tag, "tips": len(bets),
                             "units": round(sum((bet.profit or 0.0) / (bet.stake or 1.0) for bet in bets), 2)}
                            for tag, bets in tip_groups.items()), key=lambda item: -item["units"]),
        }

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


def _decided_at_halftime(leg: BetLeg, result: MatchResult) -> bool:
    """Si a la pata le alcanza el entretiempo.

    Las del 1er tiempo, y "ambas mitades más de X" cuando el 1er tiempo no pasó
    la línea: ya no pueden ser ambas, pase lo que pase en el 2º.
    """
    if leg.market_type == "both_halves_over":
        return (leg.line is not None and result.ht_home_score is not None
                and result.ht_home_score + result.ht_away_score <= leg.line)
    return leg.market_period == "HT"


def _decides(result: Optional[MatchResult], leg: BetLeg) -> bool:
    """Si ese resultado alcanza para liquidar la pata.

    El final sólo cuenta si el partido terminó (FINISHED): un suspendido o una foto
    parcial se liquidan a mano. Al 1er tiempo le alcanza el entretiempo.
    """
    if result is None:
        return False
    if result.ht_home_score is not None and _decided_at_halftime(leg, result):
        return (result.status or "").upper() in {"FINISHED", "HALFTIME"}
    return result.final_home_score is not None and (result.status or "").upper() == "FINISHED"


def _result_by_alias(leg: BetLeg, results: list[MatchResult]) -> Optional[MatchResult]:
    """El resultado que el watch archivó desde OTRA casa del mismo partido.

    El watch guarda en el crudo los ids de cada casa donde lo vio (`_event_ids`): una
    pata enlazada a solcasino encuentra el resultado archivado desde betovo aunque
    los nombres no se parezcan ("ASA Tel Aviv" / "AS Tel Aviv University").
    """
    if not leg.platform or not leg.external_event_id:
        return None
    for result in results:
        try:
            aliases = json.loads(result.raw_payload_json or "{}").get("_event_ids") or {}
        except (TypeError, ValueError, AttributeError):
            continue
        if str(aliases.get(leg.platform) or "") == str(leg.external_event_id):
            return result
    return None


def _match_text(match: Any) -> str:
    """Equipos + liga de un partido (archivado o vigente), para la guarda de categoría."""
    return " ".join(str(getattr(match, name, None) or "")
                    for name in ("home", "away", "competition_name"))


REPORT_PERIODS = {
    "day": "day", "hoy": "day", "today": "day",
    "yesterday": "yesterday", "ayer": "yesterday",
    "week": "week", "semana": "week",
    "last_week": "last_week", "semana_pasada": "last_week",
    "month": "month", "mes": "month",
    "last_month": "last_month", "mes_pasado": "last_month",
}
_MONTHS_ES = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
              "septiembre", "octubre", "noviembre", "diciembre")


def report_window(period: str, *, now: datetime, tz: ZoneInfo) -> tuple[datetime, datetime, str]:
    """(desde, hasta, título) de un período, con los días del huso del chat."""
    kind = REPORT_PERIODS.get(period)
    if kind is None:
        raise ValueError(f"período desconocido: {period}. Opciones: día, ayer, semana, mes, "
                         "semana_pasada, mes_pasado")
    local = now.astimezone(tz)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if kind == "day":
        start, end, label = today, local, f"hoy {today:%d/%m}"
    elif kind == "yesterday":
        start, end = today - timedelta(days=1), today
        label = f"{start:%d/%m}"
    elif kind == "week":
        start, end = today - timedelta(days=today.weekday()), local
        label = f"semana del {start:%d/%m}"
    elif kind == "last_week":
        end = today - timedelta(days=today.weekday())
        start = end - timedelta(days=7)
        label = f"semana del {start:%d/%m} al {end - timedelta(days=1):%d/%m}"
    elif kind == "month":
        start, end = today.replace(day=1), local
        label = f"{_MONTHS_ES[start.month - 1]} {start.year}"
    else:
        end = today.replace(day=1)
        start = (end - timedelta(days=1)).replace(day=1)
        label = f"{_MONTHS_ES[start.month - 1]} {start.year}"
    return start, end, label


def _bet_brief(bet: Bet) -> dict[str, Any]:
    leg = bet.legs[0] if bet.legs else None
    match = (f"{leg.home} vs {leg.away}" if leg and leg.home else leg.match_label if leg else "")
    return {"id": bet.id, "match": match, "bookmaker": bet.bookmaker, "status": bet.status,
            "profit_usd": round(bet.profit_usd, 2), "legs": len(bet.legs)}


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
