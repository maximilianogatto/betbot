import json

import httpx
from typing import Dict, List, Any, Optional

class PalloliittoAPI:
    """
    HTTP-only Client to extract fixtures, leagues, standings, and match details 
    from the Finnish Football Association website (https://tulospalvelu.palloliitto.fi/).
    
    This client bypasses Cloudflare checks entirely using a static accept header key
    discovered from the official web frontend.
    """
    
    BASE_URL = "https://spl.torneopal.net/taso/rest"
    
    # Custom Accept header that validates requests with the Torneopal API
    HEADERS = {
        "accept": "json/4h7dznqdxwtp3hsfdyf5r793uahfxy7x",
        "referer": "https://tulospalvelu.palloliitto.fi/",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    }

    # League hierarchy mapping (escalafón)
    # Higher levels represent higher tier professional or national leagues
    LEAGUE_HIERARCHY = {
        # Men's Adult Football
        "VL": {"name": "Veikkausliiga", "gender": "M", "level": 1, "type": "football"},
        "M1L": {"name": "Ykkösliiga", "gender": "M", "level": 2, "type": "football"},
        "M1": {"name": "Ykkönen", "gender": "M", "level": 3, "type": "football"},
        "M2": {"name": "Kakkonen", "gender": "M", "level": 4, "type": "football"},
        "M3": {"name": "Kolmonen", "gender": "M", "level": 5, "type": "football"},
        "M4": {"name": "Nelonen", "gender": "M", "level": 6, "type": "football"},
        "M5": {"name": "Vitonen", "gender": "M", "level": 7, "type": "football"},
        "M6": {"name": "Kutonen", "gender": "M", "level": 8, "type": "football"},
        "M7": {"name": "Seiska", "gender": "M", "level": 9, "type": "football"},
        
        # Women's Adult Football
        "NL": {"name": "Kansallinen Liiga", "gender": "F", "level": 1, "type": "football"},
        "N1": {"name": "Naisten Ykkönen", "gender": "F", "level": 2, "type": "football"},
        "N2": {"name": "Naisten Kakkonen", "gender": "F", "level": 3, "type": "football"},
        "N3": {"name": "Naisten Kolmonen", "gender": "F", "level": 4, "type": "football"},
        "N4": {"name": "Naisten Nelonen", "gender": "F", "level": 5, "type": "football"},
        "N5": {"name": "Naisten Vitonen", "gender": "F", "level": 6, "type": "football"},
        
        # Major Cups
        "MSC": {"name": "Suomen Cup", "gender": "M", "level": 1, "type": "cup"},
        "NSC": {"name": "Naisten Suomen Cup", "gender": "F", "level": 1, "type": "cup"},
        "LC": {"name": "Liigacup", "gender": "M", "level": 1, "type": "cup"},
        "M1LCUP": {"name": "Ykkösliigacup", "gender": "M", "level": 2, "type": "cup"}
    }

    def __init__(self, timeout: float = 60.0):
        # Some payloads (a whole day of getMatches) are ~5-6 MB; the old 15s
        # timeout + a reused keep-alive connection delivered truncated bodies.
        self._timeout = timeout
        self.client = httpx.Client(headers=self.HEADERS, timeout=timeout)

    def _reset_client(self) -> None:
        try:
            self.client.close()
        except Exception:
            pass
        self.client = httpx.Client(headers=self.HEADERS, timeout=self._timeout)

    def _request(self, method_name: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Send a request to the Torneopal REST endpoint.

        Large payloads (e.g. a whole day of `getMatches`, ~2 MB) occasionally
        arrive truncated and fail to parse. We discard a bad/incomplete body and
        re-fetch a few times before giving up, instead of crashing the command.
        """
        url = f"{self.BASE_URL}/{method_name}"
        last_error: Optional[Exception] = None
        for _attempt in range(3):
            response = self.client.get(url, params=params)
            if response.status_code != 200:
                raise RuntimeError(f"HTTP error {response.status_code}: {response.text}")
            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                last_error = exc  # truncated/garbled body -> drop the connection and re-fetch
                self._reset_client()
                continue
            call_info = data.get("call", {})
            if call_info.get("status") == "error":
                raise ValueError(f"API Error ({method_name}): {call_info.get('error')}")
            return data
        raise RuntimeError(
            f"Respuesta inválida o truncada de {method_name} tras reintentos: {last_error}"
        )

    def get_categories(self, season: str = "2026") -> List[Dict[str, Any]]:
        """
        Retrieve all league categories for the given season.
        Adds hierarchy and escalafón meta data when recognized.
        """
        # Accept comma-separated seasons as well
        data = self._request("getCategories", {"season_id": season})
        categories = data.get("categories", [])
        
        processed_categories = []
        for cat in categories:
            cat_id = cat.get("category_id")
            
            # Map hierarchy
            hierarchy = self.LEAGUE_HIERARCHY.get(cat_id, None)
            if hierarchy:
                cat["hierarchy_level"] = hierarchy["level"]
                cat["hierarchy_name"] = hierarchy["name"]
                cat["sport_type"] = hierarchy["type"]
            else:
                cat["hierarchy_level"] = 99  # Youth leagues or unclassified
                cat["hierarchy_name"] = "Unclassified / Youth"
                cat["sport_type"] = "unknown"
                
            processed_categories.append(cat)
            
        return processed_categories

    def get_matches_by_date(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Get all matches scheduled or played on a specific date (YYYY-MM-DD).
        """
        data = self._request("getMatches", {"date": date_str})
        return data.get("matches", [])

    def get_matches_by_league(self, competition_id: str, category_id: str) -> List[Dict[str, Any]]:
        """
        Get all fixtures and matches for a specific league (e.g. Veikkausliiga VL, Ykkösliiga M1L).
        """
        data = self._request("getMatches", {"competition_id": competition_id, "category_id": category_id})
        return data.get("matches", [])

    def get_standings(self, competition_id: str, category_id: str, group_id: str) -> List[Dict[str, Any]]:
        """
        Get full league standings table (rankings, points, goals, etc.) for a league group.
        """
        data = self._request("getGroup", {
            "competition_id": competition_id,
            "category_id": category_id,
            "group_id": group_id
        })
        group_data = data.get("group", {})
        return group_data.get("live_standings", []) or group_data.get("teams", [])

    def get_match_details(self, match_id: str) -> Dict[str, Any]:
        """
        Get complete match details including lineups, goals, bookings (cards), 
        timeline events, substitution events, and referees.
        """
        data = self._request("getMatch", {"match_id": match_id})
        return data.get("match", {})

    def get_team_details(self, team_id: str) -> Dict[str, Any]:
        """
        Get team and club configurations (crests, jerseys, cities, websites).
        """
        data = self._request("getTeam", {"team_id": team_id})
        return data.get("team", {})

    def get_league_ranking_list(self) -> List[Dict[str, Any]]:
        """
        Returns a beautifully formatted list of Finnish leagues sorted by their 
        official level in the football pyramid (escalafón).
        """
        sorted_leagues = []
        for cat_id, info in self.LEAGUE_HIERARCHY.items():
            sorted_leagues.append({
                "category_id": cat_id,
                "name": info["name"],
                "gender": "Men" if info["gender"] == "M" else "Women",
                "tier": info["level"],
                "sport": info["type"].capitalize()
            })
        # Sort by sport (Football first), then tier, then gender
        sorted_leagues.sort(key=lambda x: (x["sport"] != "Football", x["tier"], x["gender"] != "Men"))
        return sorted_leagues

    def close(self):
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
