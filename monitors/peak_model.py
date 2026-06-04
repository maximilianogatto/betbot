"""Pre-match mismatch model for special-league peak detection.

Pure, network-free statistics. Adapters in :mod:`monitors.special_peak` build a
:class:`LeagueModel` from the Finland / Sweden feeds and call
:func:`score_prematch`; everything here is unit-testable with synthetic data.

The model estimates how *clear* the favourite is (a "mismatch magnitude"),
which in obscure leagues is what casinos are slow to price. It folds five reads,
each gated by its own data sufficiency:

1. **Standings position gap** — gated by a logistic on games played (a small
   sample is not representative; below the midpoint the table is ignored, above
   it counts).
2. **Attack z-score (home/away aware)** — each side's scoring rate in its venue
   role vs the league-wide rate, in cross-team standard-deviation units.
3. **Defence z-score (home/away aware)** — same for goals conceded.
   (2)+(3) combine into an expected goal supremacy ``S`` (Dixon-Coles-lite); a
   team that "never scores" sinks its own ``S`` even with a close table.
4. **H2H** — recency-decayed (exp), margin via ``tanh`` (blowouts saturate),
   weight halved when a red card distorted the game.
5. **Transitivity** — common-opponent performance difference, decayed, weighted
   low (indirect evidence).

The signed combination gives the favourite and an ``edge``; its magnitude maps
to a 1-10 score. Cup rotation (B-Team) is layered on top in ``special_peak``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


# --------------------------------------------------------------------------- #
# Tunable parameters
# --------------------------------------------------------------------------- #
@dataclass
class PeakParams:
    """All knobs for the pre-match model (env/CLI-tunable later)."""

    # Data-sufficiency logistic gate on games played: w = 1/(1+e^(-k(N-N0))).
    gate_midpoint: float = 5.0
    gate_steepness: float = 1.0

    # Term weights in the signed edge (each underlying term is in [-1, 1]).
    w_supremacy: float = 1.0
    w_position: float = 0.6
    w_h2h: float = 0.7
    w_transitivity: float = 0.4

    # Scale that maps the raw summed-z supremacy into [-1, 1] via tanh.
    supremacy_scale: float = 2.5

    # H2H / transitivity recency decay (days) and red-card weight multiplier.
    decay_tau_days: float = 180.0
    red_card_weight: float = 0.5
    margin_scale: float = 2.0  # tanh(goal_diff / margin_scale)

    # Minimum cross-team std before a z-score is trusted (else treated as 0).
    min_std: float = 1e-3


# --------------------------------------------------------------------------- #
# Data structures
# --------------------------------------------------------------------------- #
@dataclass
class TeamStats:
    """Per-team season aggregates (already split by venue)."""

    team_id: str
    name: str = ""
    position: Optional[int] = None
    played: int = 0
    played_home: int = 0
    played_away: int = 0
    gf_home: int = 0
    ga_home: int = 0
    gf_away: int = 0
    ga_away: int = 0

    def _rate(self, num: int, den: int) -> Optional[float]:
        return (num / den) if den > 0 else None

    @property
    def rate_gf_home(self) -> Optional[float]:
        return self._rate(self.gf_home, self.played_home)

    @property
    def rate_ga_home(self) -> Optional[float]:
        return self._rate(self.ga_home, self.played_home)

    @property
    def rate_gf_away(self) -> Optional[float]:
        return self._rate(self.gf_away, self.played_away)

    @property
    def rate_ga_away(self) -> Optional[float]:
        return self._rate(self.ga_away, self.played_away)


@dataclass
class PastMatch:
    """One finished match used for H2H / transitivity."""

    date: str  # "YYYY-MM-DD"
    home_id: str
    away_id: str
    gh: int
    ga: int
    home_red: bool = False
    away_red: bool = False
    has_red_info: bool = False


@dataclass
class LeagueModel:
    """A competition's standings aggregates + finished-match history."""

    name: str
    teams: dict[str, TeamStats] = field(default_factory=dict)
    matches: list[PastMatch] = field(default_factory=list)

    @property
    def n_teams(self) -> int:
        return len(self.teams)


@dataclass
class PrematchBreakdown:
    """Result of scoring one fixture."""

    favorite_id: Optional[str]
    edge: float  # signed toward home team (>0 => home favoured)
    magnitude: float  # |normalised edge| in [0, 1]
    score: float  # 1..10
    components: dict[str, float]
    notes: list[str] = field(default_factory=list)

    @property
    def score_int(self) -> int:
        return int(round(self.score))


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def logistic(x: float, *, midpoint: float = 0.0, steepness: float = 1.0) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-steepness * (x - midpoint)))
    except OverflowError:
        return 0.0 if x < midpoint else 1.0


def _mean_std(values: list[float]) -> tuple[float, float]:
    """Sample mean and (population) std of a non-empty list; (0,0) if empty."""

    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    var = sum((v - mean) ** 2 for v in values) / n
    return mean, math.sqrt(var)


def _zscore(value: Optional[float], mean: float, std: float, *, min_std: float) -> float:
    if value is None or std < min_std:
        return 0.0
    return (value - mean) / std


def _parse_date(value: str) -> Optional[datetime]:
    raw = str(value or "").strip().replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


# --------------------------------------------------------------------------- #
# League-level reference rates
# --------------------------------------------------------------------------- #
@dataclass
class LeagueRates:
    mu_gf_home: float
    sd_gf_home: float
    mu_ga_home: float
    sd_ga_home: float
    mu_gf_away: float
    sd_gf_away: float
    mu_ga_away: float
    sd_ga_away: float


def league_rates(model: LeagueModel) -> LeagueRates:
    """Cross-team mean/std of per-team venue rates ('what the league generally does')."""

    gf_home = [t.rate_gf_home for t in model.teams.values() if t.rate_gf_home is not None]
    ga_home = [t.rate_ga_home for t in model.teams.values() if t.rate_ga_home is not None]
    gf_away = [t.rate_gf_away for t in model.teams.values() if t.rate_gf_away is not None]
    ga_away = [t.rate_ga_away for t in model.teams.values() if t.rate_ga_away is not None]
    m1, s1 = _mean_std(gf_home)
    m2, s2 = _mean_std(ga_home)
    m3, s3 = _mean_std(gf_away)
    m4, s4 = _mean_std(ga_away)
    return LeagueRates(m1, s1, m2, s2, m3, s3, m4, s4)


# --------------------------------------------------------------------------- #
# Individual factors
# --------------------------------------------------------------------------- #
def data_gate(team_h: TeamStats, team_a: TeamStats, params: PeakParams) -> float:
    n = min(team_h.played, team_a.played)
    return logistic(float(n), midpoint=params.gate_midpoint, steepness=params.gate_steepness)


def position_signal(team_h: TeamStats, team_a: TeamStats, n_teams: int) -> float:
    """Signed in [-1,1] toward home (home better = lower position number)."""

    if team_h.position is None or team_a.position is None or n_teams < 2:
        return 0.0
    return (team_a.position - team_h.position) / (n_teams - 1)


def expected_supremacy(
    team_h: TeamStats,
    team_a: TeamStats,
    rates: LeagueRates,
    params: PeakParams,
) -> float:
    """Summed-z goal supremacy toward home (raw z units; squash later)."""

    z_for_h = _zscore(team_h.rate_gf_home, rates.mu_gf_home, rates.sd_gf_home, min_std=params.min_std)
    z_against_a = _zscore(team_a.rate_ga_away, rates.mu_ga_away, rates.sd_ga_away, min_std=params.min_std)
    home_edge = z_for_h + z_against_a  # home scores a lot AND away concedes a lot

    z_for_a = _zscore(team_a.rate_gf_away, rates.mu_gf_away, rates.sd_gf_away, min_std=params.min_std)
    z_against_h = _zscore(team_h.rate_ga_home, rates.mu_ga_home, rates.sd_ga_home, min_std=params.min_std)
    away_edge = z_for_a + z_against_h

    return home_edge - away_edge


def h2h_signal(
    home_id: str,
    away_id: str,
    matches: list[PastMatch],
    now: datetime,
    params: PeakParams,
) -> tuple[float, int]:
    """Recency-decayed H2H signal in [-1,1] toward home; also returns sample size."""

    pair = {home_id, away_id}
    relevant = [m for m in matches if {m.home_id, m.away_id} == pair]
    if not relevant:
        return 0.0, 0

    num = 0.0
    den = 0.0
    for m in relevant:
        d = _parse_date(m.date)
        if d is None:
            weight = 0.5
        else:
            delta_days = max(0.0, (now - d).total_seconds() / 86400.0)
            weight = math.exp(-delta_days / params.decay_tau_days)
        if m.has_red_info and (m.home_red or m.away_red):
            weight *= params.red_card_weight
        # Goal diff oriented to *today's* home team.
        gd = (m.gh - m.ga) if m.home_id == home_id else (m.ga - m.gh)
        num += weight * math.tanh(gd / params.margin_scale)
        den += weight

    if den <= 0:
        return 0.0, len(relevant)
    return num / den, len(relevant)


def _perf_vs(team_id: str, opponent_id: str, matches: list[PastMatch], now: datetime, params: PeakParams) -> Optional[float]:
    """Decayed mean goal diff of ``team_id`` vs ``opponent_id`` (team's perspective)."""

    pair = {team_id, opponent_id}
    rel = [m for m in matches if {m.home_id, m.away_id} == pair]
    if not rel:
        return None
    num = 0.0
    den = 0.0
    for m in rel:
        d = _parse_date(m.date)
        weight = 1.0 if d is None else math.exp(-max(0.0, (now - d).total_seconds() / 86400.0) / params.decay_tau_days)
        gd = (m.gh - m.ga) if m.home_id == team_id else (m.ga - m.gh)
        num += weight * math.tanh(gd / params.margin_scale)
        den += weight
    return num / den if den > 0 else None


def transitivity_signal(
    home_id: str,
    away_id: str,
    matches: list[PastMatch],
    now: datetime,
    params: PeakParams,
) -> tuple[float, int]:
    """Common-opponent performance difference in [-1,1] toward home; + sample size."""

    home_opps = {m.away_id if m.home_id == home_id else m.home_id for m in matches if home_id in (m.home_id, m.away_id)}
    away_opps = {m.away_id if m.home_id == away_id else m.home_id for m in matches if away_id in (m.home_id, m.away_id)}
    common = (home_opps & away_opps) - {home_id, away_id}
    if not common:
        return 0.0, 0

    diffs = []
    for opp in common:
        ph = _perf_vs(home_id, opp, matches, now, params)
        pa = _perf_vs(away_id, opp, matches, now, params)
        if ph is not None and pa is not None:
            diffs.append(ph - pa)
    if not diffs:
        return 0.0, 0
    return math.tanh(sum(diffs) / len(diffs)), len(common)


# --------------------------------------------------------------------------- #
# Top-level scoring
# --------------------------------------------------------------------------- #
def score_prematch(
    home_id: str,
    away_id: str,
    model: LeagueModel,
    *,
    now: Optional[datetime] = None,
    params: Optional[PeakParams] = None,
) -> PrematchBreakdown:
    """Score one fixture's mismatch magnitude (1..10) from a built league model."""

    params = params or PeakParams()
    now = now or datetime.now(tz=timezone.utc)

    team_h = model.teams.get(home_id) or TeamStats(team_id=home_id)
    team_a = model.teams.get(away_id) or TeamStats(team_id=away_id)
    rates = league_rates(model)

    gate = data_gate(team_h, team_a, params)
    pos = position_signal(team_h, team_a, model.n_teams) * gate
    sup_raw = expected_supremacy(team_h, team_a, rates, params) * gate
    sup = math.tanh(sup_raw / params.supremacy_scale)
    h2h, h2h_n = h2h_signal(home_id, away_id, model.matches, now, params)
    trans, trans_n = transitivity_signal(home_id, away_id, model.matches, now, params)

    edge = (
        params.w_supremacy * sup
        + params.w_position * pos
        + params.w_h2h * h2h
        + params.w_transitivity * trans
    )
    weight_sum = params.w_supremacy + params.w_position + params.w_h2h + params.w_transitivity
    magnitude = min(1.0, abs(edge) / weight_sum) if weight_sum else 0.0
    score = 1.0 + 9.0 * magnitude

    favorite_id: Optional[str]
    if abs(edge) < 1e-9:
        favorite_id = None
    else:
        favorite_id = home_id if edge > 0 else away_id

    components = {
        "data_gate": round(gate, 3),
        "supremacy_z": round(sup_raw, 3),
        "supremacy": round(sup, 3),
        "position": round(pos, 3),
        "h2h": round(h2h, 3),
        "h2h_n": h2h_n,
        "transitivity": round(trans, 3),
        "transitivity_n": trans_n,
        "edge": round(edge, 3),
    }
    return PrematchBreakdown(
        favorite_id=favorite_id,
        edge=edge,
        magnitude=magnitude,
        score=score,
        components=components,
    )
