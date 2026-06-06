from __future__ import annotations

from html.parser import HTMLParser
from typing import Any
import httpx

class NorwayHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.current_table = []
        self.current_row = []
        self.current_cell = []
        self.current_hrefs = []
        self.in_table = False
        self.in_cell = False
        self.table_attrs = {}

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "table":
            self.in_table = True
            self.table_attrs = attrs_dict
            self.current_table = []
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = True
            self.current_cell = []
            self.current_hrefs = []
        elif tag == "a" and self.in_cell:
            if "href" in attrs_dict:
                self.current_hrefs.append(attrs_dict["href"])

    def handle_endtag(self, tag):
        if tag == "table":
            self.in_table = False
            self.tables.append({
                "attrs": self.table_attrs,
                "rows": self.current_table
            })
        elif tag in ("td", "th") and self.in_table:
            self.in_cell = False
            cell_text = "".join(self.current_cell).strip().replace("\n", " ")
            self.current_row.append({
                "text": cell_text,
                "hrefs": self.current_hrefs
            })
        elif tag == "tr" and self.in_table:
            if self.current_row:
                self.current_table.append(self.current_row)
            self.current_row = []

    def handle_data(self, data):
        if self.in_cell:
            self.current_cell.append(data)


class NorwayNFFHTTPClient:
    """HTTP scraper client for Norway NFF (fotball.no)."""

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

    def __enter__(self) -> NorwayNFFHTTPClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def get_html(self, url: str) -> str:
        resp = self.client.get(url, follow_redirects=True)
        resp.raise_for_status()
        return resp.text

    def get_tables(self, url: str) -> list[dict[str, Any]]:
        html = self.get_html(url)
        p = NorwayHTMLParser()
        p.feed(html)
        return p.tables
