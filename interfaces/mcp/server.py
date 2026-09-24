"""Servidor MCP de BetBot: lo mismo que el bot de Telegram, pensado para analizar datos.

Corre en la VPS por stdio y lo lanza el cliente MCP por SSH, así que no abre puertos:

    ssh -i ~/.ssh/betbot_vps usuario@vps \
        'cd ~/betbot && set -a && . ./.env && set +a && exec betbot/bin/python -m interfaces.mcp'

- Lectura: `schema` + `query` (SQL de sólo lectura, con tope de filas y de tiempo) para
  cualquier análisis, y vistas armadas en JSON: apuestas, P&L, exposición, ligas,
  partidos vigentes, historial de cuotas, resultados archivados y watches.
- Escritura: siempre por los services, con las mismas validaciones que /bet,
  /settle, /void_bet, /watch_live y /track_league. Nunca SQL.

Lo que en Telegram es por chat (ligas, watches, apuestas) usa `chat_id` si se pasa,
si no BETBOT_MCP_CHAT_ID, y si no el chat con más ligas suscriptas.

Los avisos a Telegram (liquidaciones, alertas) los sigue mandando el bot: este proceso
no habla con Telegram.
"""

from __future__ import annotations

from collections import defaultdict
import dataclasses
from datetime import datetime, timezone
import functools
import inspect
import json
import os
import sqlite3
import time
from typing import Any
from zoneinfo import ZoneInfo

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from adapters.storage.connection import resolve_database_path

server = MCPServer(
    name="betbot",
    instructions=(
        "Base de datos y servicios del bot de apuestas BetBot (VPS). Para analizar, empezá por "
        "`schema` y usá `query` (SQL de sólo lectura, SQLite). Las tablas clave: bets/bet_legs "
        "(libro de apuestas), events (partidos vigentes con cuotas), odds_history (serie de "
        "cuotas), match_results (resultados archivados), competitions/subscriptions (ligas "
        "trackeadas), live_watch_entries (watches). Las escrituras van por las tools *_add, "
        "*_settle, *_void, *_set, *_track, *_remove: validan igual que los comandos de Telegram. "
        "Horas en ISO-8601 UTC."
    ),
)

READ = ToolAnnotations(read_only_hint=True, open_world_hint=False)
READ_NETWORK = ToolAnnotations(read_only_hint=True, open_world_hint=True)
WRITE = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False)
WRITE_NETWORK = ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=True)

QUERY_TIMEOUT_SECONDS = 15.0
QUERY_MAX_ROWS = 5000

#: Errores de uso (dato inválido, SQL mal escrito, apuesta que no existe): su mensaje
#: tiene que llegarle al cliente. El SDK sólo lo pasa si la tool levanta ToolError;
#: cualquier otra excepción la reporta como un error genérico.
_USER_ERRORS = (ValueError, LookupError, sqlite3.Error)


def _tool(annotations: ToolAnnotations):
    """Registra la tool traduciendo los errores de uso a ToolError.

    Devuelve la función original: los tests (y quien la importe) la llaman directo.
    """

    def decorate(fn):
        if inspect.iscoroutinefunction(fn):
            @functools.wraps(fn)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return await fn(*args, **kwargs)
                except _USER_ERRORS as error:
                    raise ToolError(str(error)) from error
        else:
            @functools.wraps(fn)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                try:
                    return fn(*args, **kwargs)
                except _USER_ERRORS as error:
                    raise ToolError(str(error)) from error
        server.tool(annotations=annotations)(wrapper)
        return fn

    return decorate


# --------------------------------------------------------------------------- #
# Runtime: los services se arman a demanda (el registro de extractores pesa y
# sólo lo necesitan las tools que tocan casas).
# --------------------------------------------------------------------------- #
class _Runtime:
    def __init__(self) -> None:
        self._storage = None
        self._ledger = None
        self._live_watch = None
        self._tracking = None

    @property
    def storage(self):
        if self._storage is None:
            from adapters.storage import SqliteStorage

            self._storage = SqliteStorage()
        return self._storage

    @property
    def ledger(self):
        if self._ledger is None:
            from services.ledger import LedgerService

            self._ledger = LedgerService(self.storage)
        return self._ledger

    @property
    def live_watch(self):
        if self._live_watch is None:
            from core.registry import ExtractorRegistry
            from services.live_watch import LiveWatchService

            # Gestionar watches no consulta casas: registro vacío, arranque liviano.
            self._live_watch = LiveWatchService(
                extractor_registry=ExtractorRegistry(), repository=self.storage)
        return self._live_watch

    @property
    def tracking(self):
        if self._tracking is None:
            from bot.config import load_settings
            from core.registry import ExtractorRegistry
            from extractors import register_default_extractors
            from services.tracking import TrackingService

            registry = ExtractorRegistry()
            register_default_extractors(registry, settings=load_settings())
            self._tracking = TrackingService(extractor_registry=registry, repository=self.storage)
        return self._tracking

    def chat_id(self, chat_id: int | None) -> int:
        if chat_id is not None:
            return int(chat_id)
        configured = os.getenv("BETBOT_MCP_CHAT_ID", "").strip()
        if configured:
            return int(configured)
        with _read_connection() as conn:
            row = conn.execute(
                "SELECT chat_id FROM subscriptions WHERE enabled = 1"
                " GROUP BY chat_id ORDER BY count(*) DESC LIMIT 1").fetchone()
        if row is None:
            raise ValueError("no hay chats con ligas: pasá chat_id o configurá BETBOT_MCP_CHAT_ID")
        return int(row[0])


runtime = _Runtime()


def _plain(value: Any) -> Any:
    """Dataclasses/fechas -> JSON."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class _read_connection:
    """Conexión SQLite de sólo lectura (mode=ro + query_only), con tope de tiempo."""

    def __init__(self, timeout_seconds: float = QUERY_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds

    def __enter__(self) -> sqlite3.Connection:
        self.conn = sqlite3.connect(f"file:{resolve_database_path()}?mode=ro", uri=True, timeout=10)
        self.conn.execute("PRAGMA query_only = ON")
        deadline = time.monotonic() + self.timeout_seconds
        self.conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 10_000)
        return self.conn

    def __exit__(self, *exc: Any) -> None:
        self.conn.close()


def _json_or_none(raw: Any) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# Lectura / análisis
# --------------------------------------------------------------------------- #
@_tool(READ)
def schema(table: str | None = None) -> dict[str, Any]:
    """Tablas de la base del bot con sus columnas y cantidad de filas.

    Pasá `table` para ver sólo una. Es el punto de partida para escribir `query`.
    """
    with _read_connection() as conn:
        names = [row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            " ORDER BY name")]
        if table is not None:
            if table not in names:
                raise ValueError(f"no existe la tabla {table!r}. Tablas: {', '.join(names)}")
            names = [table]
        tables = {}
        for name in names:
            columns = [{"name": col[1], "type": col[2], "pk": bool(col[5])}
                       for col in conn.execute(f'PRAGMA table_info("{name}")')]
            rows = conn.execute(f'SELECT count(*) FROM "{name}"').fetchone()[0]
            tables[name] = {"rows": rows, "columns": columns}
    return {"database": "sqlite", "tables": tables}


@_tool(READ)
def query(sql: str, params: list[Any] | None = None, limit: int = 200) -> dict[str, Any]:
    """Consulta SQL de SÓLO LECTURA sobre la base del bot (SQLite).

    Una sola sentencia (SELECT / WITH / PRAGMA de lectura), parámetros con `?` en
    `params`. Devuelve hasta `limit` filas (máx 5000) y corta a los 15 s. Cualquier
    escritura la rechaza la propia base (conexión read-only).
    """
    limit = max(1, min(int(limit), QUERY_MAX_ROWS))
    try:
        with _read_connection() as conn:
            cursor = conn.execute(sql, list(params or []))
            columns = [description[0] for description in cursor.description or []]
            rows = cursor.fetchmany(limit + 1)
    except sqlite3.OperationalError as error:
        if "interrupted" in str(error):
            raise ValueError(f"la consulta pasó los {QUERY_TIMEOUT_SECONDS:g} s: acotala") from error
        raise ValueError(f"SQL: {error}") from error
    except sqlite3.Error as error:
        raise ValueError(f"SQL: {error}") from error
    return {"columns": columns, "rows": [list(row) for row in rows[:limit]],
            "row_count": min(len(rows), limit), "truncated": len(rows) > limit}


@_tool(READ)
def bets(status: str | None = None, mode: str | None = "real", since: str | None = None,
         bookmaker: str | None = None, tag: str | None = None, limit: int = 50) -> dict[str, Any]:
    """Apuestas del libro, las más recientes primero, con sus patas.

    - status: open | settled | won | lost | half_won | half_lost | push | void | cashout
    - mode: real | paper (None = las dos)
    - since: fecha ISO (por fecha de la apuesta)
    - bookmaker, tag: filtros exactos (tag sin '#')
    """
    sql = "SELECT id FROM bets WHERE 1 = 1"
    params: list[Any] = []
    if status == "settled":
        sql += " AND status NOT IN ('open', 'void')"
    elif status:
        sql += " AND status = ?"
        params.append(status)
    if mode:
        sql += " AND mode = ?"
        params.append(mode)
    if since:
        sql += " AND COALESCE(placed_at, created_at) >= ?"
        params.append(since)
    if bookmaker:
        sql += " AND lower(bookmaker) = lower(?)"
        params.append(bookmaker)
    if tag:
        sql += " AND (',' || lower(tags) || ',') LIKE ?"
        params.append(f"%,{tag.lstrip('#').lower()},%")
    sql += " ORDER BY COALESCE(placed_at, created_at) DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 500)))
    with _read_connection() as conn:
        ids = [row[0] for row in conn.execute(sql, params)]
    found = [runtime.storage.get_bet(bet_id) for bet_id in ids]
    return {"bets": _plain([item for item in found if item is not None])}


@_tool(READ)
def bet(bet_id: int) -> dict[str, Any]:
    """Una apuesta con todas sus patas (enlace, cuota observada, CLV, liquidación)."""
    found = runtime.storage.get_bet(int(bet_id))
    if found is None:
        raise ValueError(f"no existe la apuesta #{bet_id}")
    return _plain(found)


@_tool(READ)
def exposure() -> dict[str, Any]:
    """Exposición abierta (USD), por partido y escenario, P&L del día y límites vigentes."""
    return _plain(runtime.ledger.exposure())


_PNL_GROUPS = ("bookmaker", "family", "tag", "market", "month", "source", "status")


@_tool(READ)
def pnl(group_by: str = "bookmaker", since: str | None = None, mode: str = "real") -> dict[str, Any]:
    """P&L de las apuestas liquidadas, agrupado.

    group_by: bookmaker | family | tag | market | month | source | status. Las patas de
    una combinada cuentan como "combo" en `market`. Las apuestas sin tipo de cambio a
    USD (p. ej. ARS sin cotización) se cuentan aparte en `without_usd`.
    """
    if group_by not in _PNL_GROUPS:
        raise ValueError(f"group_by tiene que ser uno de: {', '.join(_PNL_GROUPS)}")
    sql = ("SELECT b.id, b.bookmaker, b.bookmaker_family, b.tags, b.source, b.status,"
           " COALESCE(b.settled_at, b.placed_at, b.created_at) AS settled_at, b.stake_usd,"
           " b.profit_usd, (SELECT group_concat(l.market_type) FROM bet_legs l"
           " WHERE l.bet_id = b.id) AS markets"
           " FROM bets b WHERE b.mode = ? AND b.status NOT IN ('open', 'void')")
    params: list[Any] = [mode]
    if since:
        sql += " AND COALESCE(b.settled_at, b.placed_at, b.created_at) >= ?"
        params.append(since)
    with _read_connection() as conn:
        rows = conn.execute(sql, params).fetchall()

    groups: dict[str, dict[str, float]] = defaultdict(
        lambda: {"bets": 0, "staked_usd": 0.0, "profit_usd": 0.0, "won": 0, "lost": 0})
    without_usd = 0
    for (_, bookmaker_name, family, tags, source, status_value, settled_at, stake_usd,
         profit_usd, markets) in rows:
        if stake_usd is None or profit_usd is None:
            without_usd += 1
            continue
        market_list = (markets or "").split(",")
        keys = {
            "bookmaker": [bookmaker_name or "?"], "family": [family or "?"],
            "tag": [t for t in (tags or "").split(",") if t] or ["(sin tag)"],
            "market": [market_list[0] if len(market_list) == 1 else "combo"],
            "month": [(settled_at or "?")[:7]], "source": [source or "?"],
            "status": [status_value],
        }[group_by]
        for key in keys:
            group = groups[key]
            group["bets"] += 1
            group["staked_usd"] += stake_usd
            group["profit_usd"] += profit_usd
            group["won"] += status_value in {"won", "half_won"}
            group["lost"] += status_value in {"lost", "half_lost"}
    result = []
    for key, group in sorted(groups.items(), key=lambda item: -item[1]["profit_usd"]):
        staked = group["staked_usd"]
        result.append({group_by: key, "bets": group["bets"], "staked_usd": round(staked, 2),
                       "profit_usd": round(group["profit_usd"], 2),
                       "roi": round(group["profit_usd"] / staked, 4) if staked else None,
                       "win_rate": round(group["won"] / group["bets"], 4) if group["bets"] else None})
    total_staked = sum(group["staked_usd"] for group in groups.values())
    total_profit = sum(group["profit_usd"] for group in groups.values())
    return {"groups": result, "without_usd": without_usd,
            "total": {"bets": sum(group["bets"] for group in groups.values()) if group_by != "tag"
                      else len(rows) - without_usd,
                      "staked_usd": round(total_staked, 2) if group_by != "tag" else None,
                      "profit_usd": round(total_profit, 2) if group_by != "tag" else None}}


@_tool(READ)
def report(period: str = "week", chat_id: int | None = None) -> dict[str, Any]:
    """Reporte del libro de un período, con los días del huso del chat.

    period: day | yesterday | week | last_week | month | last_month (también en
    castellano: hoy, ayer, semana, mes...). Lo mismo que /report y los reportes que
    el bot manda solo: P&L y ROI en USD, conteos por resultado, por casa, etiqueta y
    mercado, mejor y peor apuesta, exposición abierta y tips en papel por fuente.
    """
    from services.ledger import report_window
    from services.timezones import resolve_chat_timezone

    chat = runtime.chat_id(chat_id)
    since, until, label = report_window(period, now=_now(), tz=resolve_chat_timezone(chat))
    return _plain(runtime.ledger.report(since, until, chat_id=chat, label=label))


@_tool(READ)
def leagues(chat_id: int | None = None) -> dict[str, Any]:
    """Ligas trackeadas del chat: casa, URL, partidos activos, último refresh y racha sin partidos."""
    chat = runtime.chat_id(chat_id)
    with _read_connection() as conn:
        rows = conn.execute(
            "SELECT c.id, c.platform, c.name, c.source_url, c.unified_competition_id,"
            " c.last_refreshed_at, c.consecutive_unavailable_refreshes, c.last_unavailable_reason,"
            " (SELECT count(*) FROM events e WHERE e.competition_id = c.id AND e.is_active = 1)"
            " FROM competitions c JOIN subscriptions s ON s.competition_id = c.id"
            " WHERE s.chat_id = ? AND s.enabled = 1 AND c.enabled = 1 ORDER BY c.platform, c.name",
            (chat,)).fetchall()
    keys = ("id", "platform", "name", "source_url", "unified_competition_id", "last_refreshed_at",
            "empty_streak", "last_empty_reason", "active_events")
    return {"chat_id": chat, "leagues": [dict(zip(keys, row)) for row in rows]}


@_tool(READ)
def events(chat_id: int | None = None, competition_id: int | None = None, team: str | None = None,
           only_future: bool = True, with_markets: bool = False, limit: int = 100) -> dict[str, Any]:
    """Partidos vigentes de las ligas del chat, con cuotas 1X2 (y mercados si with_markets).

    - team: filtro por texto en local o visitante (sin distinguir mayúsculas)
    - with_markets: incluye hándicap/líneas de gol aplanados (market_type, period, line, side, odds)
    """
    from core.odds_markets import flatten_markets

    now = _now().isoformat()
    rows = runtime.storage.get_all_active_events_with_league(runtime.chat_id(chat_id))
    selected = []
    for row in sorted(rows, key=lambda r: (r.get("scheduled_at") or "9999", r.get("id") or 0)):
        if competition_id is not None and row.get("competition_id") != int(competition_id):
            continue
        if team and team.lower() not in f"{row.get('home')} {row.get('away')}".lower():
            continue
        if only_future and row.get("scheduled_at") and row["scheduled_at"] < now:
            continue
        item = {key: row.get(key) for key in (
            "id", "competition_id", "league_name", "platform", "external_event_id", "home", "away",
            "scheduled_at", "odds_home", "odds_draw", "odds_away", "event_url", "last_seen_at")}
        if with_markets:
            item["markets"] = flatten_markets(_json_or_none(row.get("markets_json")),
                                              home=row.get("home") or "", away=row.get("away") or "")
        selected.append(item)
        if len(selected) >= max(1, min(int(limit), 1000)):
            break
    return {"events": selected}


@_tool(READ)
def odds_history(platform: str, external_event_id: str, flatten: bool = True,
                 limit: int = 500) -> dict[str, Any]:
    """Serie de cuotas archivada de un partido (cada cambio que vio el bot), en orden.

    Con flatten=True cada captura trae sus mercados aplanados (market_type, market_period,
    line, side, odds, overround); si no, el JSON crudo de mercados.
    """
    from core.odds_markets import flatten_markets

    snapshots = runtime.storage.list_snapshots(
        platform=platform, external_event_id=str(external_event_id),
        limit=max(1, min(int(limit), 5000)))
    series = []
    for snapshot in snapshots:
        markets = _json_or_none(snapshot.markets_json)
        item = {"captured_at": snapshot.captured_at, "status": snapshot.status,
                "odds_home": snapshot.odds_home, "odds_draw": snapshot.odds_draw,
                "odds_away": snapshot.odds_away}
        item["markets"] = (flatten_markets(markets, home=snapshot.home or "", away=snapshot.away or "")
                           if flatten else markets)
        series.append(item)
    home = snapshots[0].home if snapshots else None
    away = snapshots[0].away if snapshots else None
    return {"platform": platform, "external_event_id": str(external_event_id), "home": home,
            "away": away, "snapshots": series}


@_tool(READ)
def results(team: str | None = None, since: str | None = None, only_finished: bool = False,
            limit: int = 100) -> dict[str, Any]:
    """Resultados archivados (los guarda el watch al terminar un partido), más recientes primero."""
    sql = "SELECT * FROM match_results WHERE 1 = 1"
    params: list[Any] = []
    if team:
        sql += " AND (lower(home) LIKE ? OR lower(away) LIKE ?)"
        params += [f"%{team.lower()}%"] * 2
    if since:
        sql += " AND COALESCE(kickoff_at, recorded_at) >= ?"
        params.append(since)
    if only_finished:
        sql += " AND status = 'FINISHED'"
    sql += " ORDER BY COALESCE(kickoff_at, recorded_at) DESC, id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 2000)))
    with _read_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(row) for row in conn.execute(sql, params)]
    for row in rows:
        row.pop("raw_payload_json", None)
    return {"results": rows}


@_tool(READ)
def watches(chat_id: int | None = None, status: str | None = None) -> dict[str, Any]:
    """Partidos en vigilancia (/watching): watching = esperando, fired = ya salió en vivo."""
    chat = runtime.chat_id(chat_id)
    return {"chat_id": chat, "watches": _plain(runtime.live_watch.list_watches(chat, status=status))}


@_tool(READ_NETWORK)
async def leagues_search(platform: str, country: str = "", query: str | None = None,
                         limit: int = 50) -> dict[str, Any]:
    """Busca ligas trackeables en una casa (como /track_league): consulta la casa en vivo.

    platform: 1xbet_http, betovo_http, betwarrior_http, mrpunter_http, mystake_http,
    solcasino_http. country vacío = todos.
    """
    options = await runtime.tracking.search_discoverable_leagues(
        platform=platform, country_name=country, query=query, limit=max(1, min(int(limit), 500)))
    return {"leagues": [
        {"platform": option.platform, "league_id": option.league_id,
         "league_name": option.league_name, "country": option.country_name,
         "games_count": option.games_count, "source_url": option.source_url}
        for option in options]}


# --------------------------------------------------------------------------- #
# Escritura (por los services)
# --------------------------------------------------------------------------- #
@_tool(WRITE)
def bet_add(text: str | None = None, legs: list[dict[str, Any]] | None = None,
            stake: float | None = None, currency: str = "USD", odds_total: float | None = None,
            bookmaker: str | None = None, ticket_id: str | None = None,
            placed_at: str | None = None, tags: list[str] | None = None,
            notes: str | None = None, paper: bool = False, chat_id: int | None = None,
            watch: bool = True) -> dict[str, Any]:
    """Registra una apuesta, como /bet (o /tip con paper=True).

    Dos formas:
    - text: la misma sintaxis de /bet, p. ej. "San Marino u21 vs Kosovo u21 Kosovo -3.5 @1.62
      12usd pre melbet #franko".
    - legs: patas estructuradas [{match_label, market_type, side, odds, line?, market_period?,
      team?, placed_phase?, placed_minute?}] + stake/currency/odds_total/bookmaker. Para un Bet
      Builder poné odds 0 en las patas y la cuota combinada en odds_total.

    ticket_id evita duplicados (si ya existe, no la carga). placed_at en ISO UTC. Si el
    partido no está trackeado y watch=True, lo pone en /watching para liquidarla sola.
    """
    from core.betting import parse_bet_text
    from core.betting.models import BetInput, LegInput

    if (text is None) == (legs is None):
        raise ValueError("pasá text o legs (uno de los dos)")
    if ticket_id:
        with _read_connection() as conn:
            existing = conn.execute("SELECT id FROM bets WHERE ticket_id = ?", (str(ticket_id),)).fetchone()
        if existing:
            return {"duplicate": True, "bet": bet(existing[0])}
    chat = runtime.chat_id(chat_id)
    if text is not None:
        parsed = parse_bet_text(text, now=_now(), source="mcp", paper=paper)
        bet_input, parse_notes = parsed.bet, list(parsed.notes)
    else:
        if stake is None:
            raise ValueError("con legs hace falta stake")
        bet_input = BetInput(
            legs=[LegInput(**leg) for leg in legs], stake=float(stake), currency=currency.upper(),
            odds_total=odds_total, bookmaker=bookmaker.lower() if bookmaker else None,
            source="mcp", mode="paper" if paper else "real")
        parse_notes = []
    bet_input.chat_id = chat
    if ticket_id:
        bet_input.ticket_id = str(ticket_id)
    if placed_at:
        bet_input.placed_at = placed_at
    if tags:
        bet_input.tags = list(dict.fromkeys([*bet_input.tags, *(t.lstrip("#") for t in tags)]))
    if notes:
        bet_input.notes = notes
    result = runtime.ledger.add_bet(bet_input)
    watched = []
    if watch and result.bet.status == "open":
        watched = runtime.live_watch.watch_bet(chat, result.bet)
    return {"bet": _plain(result.bet), "warnings": [*parse_notes, *result.warnings],
            "watched": _plain(watched)}


@_tool(WRITE)
def bet_settle(bet_id: int, status: str, return_amount: float | None = None,
               note: str | None = None) -> dict[str, Any]:
    """Liquida a mano, como /settle: won | lost | half_won | half_lost | push | void | cashout.

    return_amount (lo cobrado, en la moneda de la apuesta) sólo hace falta en un cashout.
    """
    return _plain(runtime.ledger.settle_manual(int(bet_id), status, return_amount=return_amount,
                                               note=note))


@_tool(ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         open_world_hint=False))
def bet_void(bet_id: int, reason: str = "anulada por el usuario") -> dict[str, Any]:
    """Anula una apuesta cargada por error, como /void_bet (sale de la exposición y del P&L)."""
    return _plain(runtime.ledger.void_bet(int(bet_id), reason))


@_tool(WRITE)
def limit_set(key: str, value: float | None) -> dict[str, Any]:
    """Fija o borra (value=None) un límite del libro, como /set_limit.

    key: max_stake_per_bet_usd | max_exposure_per_match_usd | max_open_exposure_usd |
    daily_stop_loss_usd | max_bets_per_match. Los límites avisan, no bloquean.
    """
    from core.betting.models import DEFAULT_LIMITS

    if key not in DEFAULT_LIMITS:
        raise ValueError(f"key tiene que ser uno de: {', '.join(DEFAULT_LIMITS)}")
    runtime.ledger.set_limit(key, value)
    return {"limits": runtime.storage.get_limits()}


@_tool(WRITE)
def settlement_run() -> dict[str, Any]:
    """Corre ya el enlace tardío + liquidación automática (el bot lo hace cada 10 min).

    Ojo: lo que se liquide acá no genera el aviso en Telegram (lo manda el job del bot).
    """
    settled = runtime.ledger.run_settlement()
    return {"settled": _plain(settled)}


@_tool(WRITE)
def watch_add(lines: list[str], chat_id: int | None = None,
              timezone_name: str | None = None) -> dict[str, Any]:
    """Pone partidos en vigilancia, como /watch_live. Un partido por línea:
    "Local - Visitante", "Liga | Local - Visitante" o "HH:MM Liga | Local - Visitante".

    La hora se interpreta en timezone_name (p. ej. "Europe/Madrid"); si no, en la del chat.
    Los que ya estaban en vigilancia no se duplican.
    """
    chat = runtime.chat_id(chat_id)
    added = runtime.live_watch.add_fixture_lines(
        chat, lines, times_tz=ZoneInfo(timezone_name) if timezone_name else None)
    return {"added": _plain(added)}


@_tool(ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         open_world_hint=False))
def watch_remove(watch_id: int, chat_id: int | None = None) -> dict[str, Any]:
    """Saca un partido de la vigilancia, como /unwatch (id global del watch, ver `watches`)."""
    removed = runtime.live_watch.remove_watch(runtime.chat_id(chat_id), int(watch_id))
    return {"removed": removed}


@_tool(WRITE_NETWORK)
async def league_track(platform: str, league_id: str | None = None, source_url: str | None = None,
                       chat_id: int | None = None) -> dict[str, Any]:
    """Trackea una liga en el chat, como /track_league: por league_id (de `leagues_search`)
    o por source_url. Consulta la casa para validar y cargar los partidos."""
    chat = runtime.chat_id(chat_id)
    tracking = runtime.tracking
    url = source_url
    if url is None:
        if league_id is None:
            raise ValueError("pasá league_id o source_url")
        extractor = tracking.extractor_registry.get_for_platform(platform)
        url = extractor.build_competition_url(competition_external_id=str(league_id))
        if not url:
            raise ValueError(f"{platform} no arma URLs por id: pasá source_url")
    pending = await tracking.create_pending_track_from_url(chat, url)
    if not pending.ok:
        return {"ok": False, "message": pending.message}
    request = runtime.storage.get_latest_pending_competition_request(chat)
    if request is not None and request.requires_empty_confirmation:
        confirmed = await tracking.confirm_empty_pending_track(chat)
    else:
        confirmed = await tracking.confirm_pending_track(chat)
    return {"ok": confirmed.ok, "message": confirmed.message}


@_tool(ToolAnnotations(read_only_hint=False, destructive_hint=True,
                                         open_world_hint=False))
def league_untrack(league_id: int, chat_id: int | None = None) -> dict[str, Any]:
    """Deja de trackear una liga en el chat, como /untrack (id de `leagues`)."""
    result = runtime.tracking.untrack_chat(runtime.chat_id(chat_id), int(league_id))
    return {"ok": result.ok, "message": result.message}
