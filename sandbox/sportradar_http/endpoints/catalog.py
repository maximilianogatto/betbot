from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class EndpointSpec:
    name: str
    path_template: str
    namespace: str = "bet365"
    timezone: str = "Etc:UTC"
    params: tuple[str, ...] = ()
    stability: str = "observed"
    utility: str = ""
    prematch: bool = False
    live: bool = False
    expected_payload: str = "gismo doc JSON"
    notes: str = ""

    def path(self, **kwargs: Any) -> str:
        return self.path_template.format(**{key: str(value).strip("/") for key, value in kwargs.items()})


ENDPOINT_SPECS: dict[str, EndpointSpec] = {
    "config_tree_mini": EndpointSpec(
        name="config_tree_mini",
        path_template="config_tree_mini/{category_id}/{depth}/{sport_id}",
        params=("category_id", "depth", "sport_id"),
        utility="sport/category/league navigation tree",
        prematch=True,
        notes="Large payload. Useful for discovery bootstrap.",
    ),
    "unified_sport_matches": EndpointSpec(
        name="unified_sport_matches",
        path_template="unified_sport_matches/{sport_id}/{date}/{cursor}",
        timezone="America:Montevideo",
        params=("sport_id", "date", "cursor"),
        utility="sport-level fixtures by date",
        prematch=True,
        notes="Core discovery endpoint for fixtures.",
    ),
    "unified_sport_matches_markets": EndpointSpec(
        name="unified_sport_matches_markets",
        path_template="unified_sport_matches_markets/{sport_id}/{date}/{cursor}",
        timezone="America:Montevideo",
        params=("sport_id", "date", "cursor"),
        utility="sport-level fixtures with market references",
        prematch=True,
        notes="Good candidate for odds-server discovery.",
    ),
    "sport_matches_prevnext": EndpointSpec(
        name="sport_matches_prevnext",
        path_template="sport_matches_prevnext/{sport_id}/{date}/{cursor}",
        namespace="common",
        timezone="America:Montevideo",
        params=("sport_id", "date", "cursor"),
        utility="previous/next sport fixtures cursor",
        prematch=True,
    ),
    "stats_sport_matches_prevnext": EndpointSpec(
        name="stats_sport_matches_prevnext",
        path_template="stats_sport_matches_prevnext/{sport_id}/{date}/{cursor}",
        namespace="common",
        timezone="America:Montevideo",
        params=("sport_id", "date", "cursor"),
        utility="stats-aware previous/next sport fixtures cursor",
        prematch=True,
    ),
    "stats_season_leaguesummary": EndpointSpec(
        name="stats_season_leaguesummary",
        path_template="stats_season_leaguesummary/{season_id}",
        namespace="common",
        params=("season_id",),
        utility="league summary metadata",
        prematch=True,
    ),
    "stats_season_fixtures2": EndpointSpec(
        name="stats_season_fixtures2",
        path_template="stats_season_fixtures2/{season_id}",
        params=("season_id",),
        utility="season fixtures",
        prematch=True,
    ),
    "stats_season_meta": EndpointSpec(
        name="stats_season_meta",
        path_template="stats_season_meta/{season_id}",
        params=("season_id",),
        utility="season metadata",
        prematch=True,
    ),
    "stats_season_tables": EndpointSpec(
        name="stats_season_tables",
        path_template="stats_season_tables/{season_id}/{table_id}/",
        params=("season_id", "table_id"),
        utility="standings/table",
        prematch=True,
        notes="Observed table_id can be empty string or 1.",
    ),
    "stats_formtable": EndpointSpec(
        name="stats_formtable",
        path_template="stats_formtable/{season_id}",
        params=("season_id",),
        utility="form table",
        prematch=True,
    ),
    "stats_season_teams2": EndpointSpec(
        name="stats_season_teams2",
        path_template="stats_season_teams2/{season_id}",
        params=("season_id",),
        utility="season teams",
        prematch=True,
    ),
    "stats_season_venues": EndpointSpec(
        name="stats_season_venues",
        path_template="stats_season_venues/{season_id}",
        params=("season_id",),
        utility="season venues",
        prematch=True,
    ),
    "season_markets": EndpointSpec(
        name="season_markets",
        path_template="season_markets/{season_id}",
        params=("season_id",),
        utility="season market metadata",
        prematch=True,
    ),
    "odds_ukformat": EndpointSpec(
        name="odds_ukformat",
        path_template="odds_ukformat/",
        namespace="common",
        utility="odds format/config",
        prematch=True,
        live=True,
    ),
    "match_markets": EndpointSpec(
        name="match_markets",
        path_template="match_markets/{match_id}",
        params=("match_id",),
        utility="match odds/markets",
        prematch=True,
        live=True,
    ),
    "uniqueteam_markets": EndpointSpec(
        name="uniqueteam_markets",
        path_template="uniqueteam_markets/{team_id}",
        params=("team_id",),
        utility="team market metadata",
        prematch=True,
    ),
    "match_info_statshub": EndpointSpec(
        name="match_info_statshub",
        path_template="match_info_statshub/{match_id}",
        params=("match_id",),
        utility="match metadata: teams, season, kickoff",
        prematch=True,
        live=True,
    ),
    "stats_match_get": EndpointSpec(
        name="stats_match_get",
        path_template="stats_match_get/{match_id}",
        params=("match_id",),
        utility="match snapshot/status/stats",
        prematch=True,
        live=True,
    ),
    "match_details": EndpointSpec(
        name="match_details",
        path_template="match_details/{match_id}",
        params=("match_id",),
        utility="detailed match stats",
        prematch=True,
        live=True,
    ),
    "stats_match_head2head": EndpointSpec(
        name="stats_match_head2head",
        path_template="stats_match_head2head/{match_id}",
        params=("match_id",),
        utility="match H2H context",
        prematch=True,
    ),
    "stats_match_tableslice": EndpointSpec(
        name="stats_match_tableslice",
        path_template="stats_match_tableslice/{match_id}",
        params=("match_id",),
        utility="table slice around match teams",
        prematch=True,
    ),
    "stats_h2h_versus": EndpointSpec(
        name="stats_h2h_versus",
        path_template="stats_h2h_versus/{team_a_id}/{team_b_id}/{match_id}",
        params=("team_a_id", "team_b_id", "match_id"),
        utility="direct H2H matches",
        prematch=True,
    ),
    "stats_team_versus": EndpointSpec(
        name="stats_team_versus",
        path_template="stats_team_versus/{team_a_id}/{team_b_id}/",
        params=("team_a_id", "team_b_id"),
        utility="team-vs-team context",
        prematch=True,
    ),
    "stats_team_lastx": EndpointSpec(
        name="stats_team_lastx",
        path_template="stats_team_lastx/{team_id}/{count}",
        params=("team_id", "count"),
        utility="recent team matches",
        prematch=True,
    ),
    "stats_team_nextx": EndpointSpec(
        name="stats_team_nextx",
        path_template="stats_team_nextx/{team_id}/{count}",
        params=("team_id", "count"),
        utility="upcoming team matches",
        prematch=True,
    ),
    "stats_team_streaks": EndpointSpec(
        name="stats_team_streaks",
        path_template="stats_team_streaks/{team_id}",
        namespace="common",
        params=("team_id",),
        utility="team streaks/form signals",
        prematch=True,
    ),
    "stats_season_teamscoringconceding": EndpointSpec(
        name="stats_season_teamscoringconceding",
        path_template="stats_season_teamscoringconceding/{season_id}/{team_id}/{split_id}",
        namespace="common",
        params=("season_id", "team_id", "split_id"),
        utility="goals scored/conceded distributions",
        prematch=True,
    ),
    "stats_season_injuries": EndpointSpec(
        name="stats_season_injuries",
        path_template="stats_season_injuries/{season_id}",
        params=("season_id",),
        utility="season injuries",
        prematch=True,
    ),
    "stats_season_topgoals": EndpointSpec(
        name="stats_season_topgoals",
        path_template="stats_season_topgoals/{season_id}/{team_id}",
        params=("season_id", "team_id"),
        utility="top scorers",
        prematch=True,
    ),
    "stats_season_topcards": EndpointSpec(
        name="stats_season_topcards",
        path_template="stats_season_topcards/{season_id}/{team_id}",
        params=("season_id", "team_id"),
        utility="top cards",
        prematch=True,
    ),
    "stats_season_topassists": EndpointSpec(
        name="stats_season_topassists",
        path_template="stats_season_topassists/{season_id}/{team_id}",
        params=("season_id", "team_id"),
        utility="top assists",
        prematch=True,
    ),
    "match_timeline": EndpointSpec(
        name="match_timeline",
        path_template="match_timeline/{match_id}",
        params=("match_id",),
        utility="full match timeline",
        live=True,
    ),
    "match_timelinedelta": EndpointSpec(
        name="match_timelinedelta",
        path_template="match_timelinedelta/{match_id}",
        params=("match_id",),
        utility="timeline deltas/polling",
        live=True,
    ),
    "event_get": EndpointSpec(
        name="event_get",
        path_template="event_get/",
        utility="event/live polling feed",
        live=True,
    ),
    "stats_match_situation": EndpointSpec(
        name="stats_match_situation",
        path_template="stats_match_situation/{match_id}",
        namespace="common",
        params=("match_id",),
        utility="live match situation",
        live=True,
    ),
}


def get_spec(name: str) -> EndpointSpec:
    try:
        return ENDPOINT_SPECS[name]
    except KeyError as exc:
        raise KeyError(f"Unknown Sportradar endpoint spec: {name}") from exc


def call_endpoint(client: Any, name: str, **kwargs: Any) -> dict[str, Any]:
    spec = get_spec(name)
    return client.get_gismo(
        spec.path(**kwargs),
        namespace=spec.namespace,
        timezone=spec.timezone,
    )


def extract_doc_data(payload: dict[str, Any]) -> object | None:
    doc = payload.get("doc")
    if not isinstance(doc, list) or not doc or not isinstance(doc[0], dict):
        return None
    return doc[0].get("data")


def render_endpoint_catalog_v2() -> str:
    lines = [
        "# Sportradar Endpoint Catalog v2",
        "",
        "This catalog is generated from typed endpoint specs in `sandbox/sportradar_http/endpoints/catalog.py`.",
        "",
        "| Endpoint | Path | Params | Namespace | Prematch | Live | Utility | Stability | Notes |",
        "|---|---|---|---|---:|---:|---|---|---|",
    ]
    for name in sorted(ENDPOINT_SPECS):
        spec = ENDPOINT_SPECS[name]
        lines.append(
            "| `{name}` | `{path}` | `{params}` | `{namespace}` | `{prematch}` | `{live}` | {utility} | {stability} | {notes} |".format(
                name=spec.name,
                path=spec.path_template,
                params=", ".join(spec.params) or "-",
                namespace=f"{spec.namespace}/{spec.timezone}",
                prematch="yes" if spec.prematch else "no",
                live="yes" if spec.live else "no",
                utility=spec.utility,
                stability=spec.stability,
                notes=spec.notes or "-",
            )
        )
    lines.extend(
        [
            "",
            "## Replay Requirements",
            "",
            "- Signed token `T=exp~acl~data~hmac` from browser bootstrap.",
            "- `origin: https://statshub.sportradar.com`.",
            "- `referer: https://statshub.sportradar.com/`.",
            "- Browser must not stay open after bootstrap.",
        ]
    )
    return "\n".join(lines) + "\n"

