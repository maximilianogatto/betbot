from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
import httpx

class AlgeriaMatchesParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = []
        self.current_row = []
        self.current_cell = []
        self.current_hrefs = []
        self.in_cell = False
        self.in_table = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.in_table = True
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = True
            self.current_cell = []
            self.current_hrefs = []
        elif tag == "a" and self.in_cell:
            attrs_dict = dict(attrs)
            if "href" in attrs_dict:
                self.current_hrefs.append(attrs_dict["href"])

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = False
            cell_text = "".join(self.current_cell).strip().replace("\n", " ")
            self.current_row.append({
                "text": cell_text,
                "hrefs": self.current_hrefs
            })
        elif tag == "tr" and self.in_table:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


class AlgeriaLNFFHTTPClient:
    """HTTP scraper client for Algeria LNFF."""

    def __init__(self, *, timeout: float = 20.0, client: httpx.Client | None = None) -> None:
        self._owns_client = client is None
        self.client = client or httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
                ),
            },
        )

    def close(self) -> None:
        if self._owns_client:
            self.client.close()

    def __enter__(self) -> AlgeriaLNFFHTTPClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_matches(self, path: str = "matchs-d1-seniors/") -> list[dict[str, Any]]:
        url = f"https://lnff.dz/{path.lstrip('/')}"
        resp = self.client.get(url, follow_redirects=True)
        resp.raise_for_status()
        p = AlgeriaMatchesParser()
        p.feed(resp.text)

        matches = []
        rows = p.rows
        n_blocks = len(rows) // 3
        for i in range(n_blocks):
            div_row = rows[3*i]
            date_row = rows[3*i + 1]
            match_row = rows[3*i + 2]

            if len(match_row) >= 3:
                home = match_row[0]["text"]
                score = match_row[1]["text"]
                away = match_row[2]["text"]
                match_url = match_row[1]["hrefs"][0] if match_row[1]["hrefs"] else ""
                date_str = date_row[0]["text"] if date_row else ""
                div_str = div_row[0]["text"] if div_row else ""

                matches.append({
                    "division": div_str,
                    "date_raw": date_str,
                    "home": home,
                    "away": away,
                    "score_raw": score,
                    "match_url": match_url
                })
        return matches
