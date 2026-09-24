"""Cotizaciones del dólar en Argentina desde dolarhoy.com (HTML plano, sin navegador).

La portada trae cada cotización como un bloque con su título y los valores de
compra y venta:

    <a class="titleText" href="/cotizaciondolarblue">Dólar blue</a>
    ... <div class="compra"> ... <div class="val">$1.540</div>
    ... <div class="venta"> ... <div class="val">$1.560</div>

Los montos vienen con formato argentino ("$1.539,70"). El sitio repite bloques para
la versión móvil: se toma el primero de cada tipo.

No publica USDT: lo más cercano es el "Dólar Digital (USDC)", una stablecoin que en
pesos cotiza a la par del USDT (tipo "digital"). Su link apunta a la página del
oficial, así que ese bloque se reconoce por el nombre y no por el link.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional

import httpx

DOLARHOY_URL = "https://dolarhoy.com/"
_USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/129.0 Safari/537.36")

#: slug del link de cada cotización -> clave corta
_KINDS = {
    "cotizaciondolarblue": "blue",
    "cotizaciondolaroficial": "oficial",
    "cotizaciondolarbolsa": "mep",
    "cotizaciondolarcontadoconliqui": "ccl",
    "cotizaciondolarcripto": "cripto",
    "dolar-tarjeta": "tarjeta",
    "cotizacion-dolar-tarjeta": "tarjeta",
}
#: tipos que se reconocen por el nombre (el link no alcanza)
_NAME_KINDS = ((re.compile(r"digital|usdc|usdt", re.IGNORECASE), "digital"),
               (re.compile(r"cripto", re.IGNORECASE), "cripto"))
_TITLE_RE = re.compile(r'<a class="titleText" href="/([^"]+)"[^>]*>([^<]+)</a>')
_VALUE_RE = r'<div class="{side}">.*?<div class="val"[^>]*>\s*\$?\s*([\d.,]+)\s*</div>'
_UPDATED_RE = re.compile(r"Actualizado por última vez:\s*([^<]+)<")


@dataclass(frozen=True)
class DollarQuote:
    kind: str
    name: str
    buy: Optional[float]
    sell: Optional[float]
    updated: Optional[str] = None

    @property
    def mid(self) -> Optional[float]:
        """Promedio de compra y venta (o el único valor que haya)."""
        if self.buy is not None and self.sell is not None:
            return round((self.buy + self.sell) / 2, 2)
        return self.sell if self.sell is not None else self.buy


def parse_amount(raw: str) -> float:
    """ "$1.539,70" -> 1539.7 (punto de miles, coma decimal)."""
    return float(raw.strip().lstrip("$").strip().replace(".", "").replace(",", "."))


def parse_quotes(html: str) -> dict[str, DollarQuote]:
    """Cotizaciones de la portada por tipo: blue, oficial, mep, ccl, digital (USDC), tarjeta."""
    titles = list(_TITLE_RE.finditer(html))
    quotes: dict[str, DollarQuote] = {}
    for index, title in enumerate(titles):
        name = title.group(2).strip()
        kind = next((kind for pattern, kind in _NAME_KINDS if pattern.search(name)), None) \
            or _KINDS.get(title.group(1).strip("/").lower())
        if kind is None or kind in quotes:
            continue
        end = titles[index + 1].start() if index + 1 < len(titles) else len(html)
        block = html[title.end():end]
        values = {}
        for side in ("compra", "venta"):
            match = re.search(_VALUE_RE.format(side=side), block, re.DOTALL)
            values[side] = parse_amount(match.group(1)) if match else None
        if values["compra"] is None and values["venta"] is None:
            continue
        updated = _UPDATED_RE.search(block)
        quotes[kind] = DollarQuote(kind=kind, name=name, buy=values["compra"],
                                   sell=values["venta"],
                                   updated=updated.group(1).strip() if updated else None)
    return quotes


async def fetch_quotes(*, timeout: float = 20.0,
                       client: httpx.AsyncClient | None = None) -> dict[str, DollarQuote]:
    """Baja la portada de dolarhoy.com y devuelve sus cotizaciones."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                         headers={"user-agent": _USER_AGENT})
    try:
        response = await client.get(DOLARHOY_URL)
        response.raise_for_status()
        quotes = parse_quotes(response.text)
    finally:
        if owns_client:
            await client.aclose()
    if not quotes:
        raise ValueError("dolarhoy.com no trajo cotizaciones: ¿cambió el HTML?")
    return quotes
