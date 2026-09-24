"""Extractor de cotizaciones de dolarhoy.com (HTML real recortado, 2026-09-24)."""
from __future__ import annotations

import unittest

import httpx

from adapters.fx.dolarhoy import DOLARHOY_URL, fetch_quotes, parse_amount, parse_quotes


def _block(href: str, name: str, buy: str, sell: str, extra: str = "") -> str:
    return (f'<div class="tile is-child"><div class="title"><a class="titleText" href="{href}"'
            f' aria-label="Link a {name}">{name} </a>{extra}</div><div class="values">'
            f'<div class="compra"><div class="label">Compra</div><div class="val" style="color:#005c35">'
            f'{buy}</div><div class="label"></div></div><div class="separator"></div><div class="venta">'
            f'<div class="venta-wrapper"><div class="label">Venta</div><div class="val">{sell}</div></div>'
            f'<div class="var-porcentaje"><div>0.00%</div></div></div></div></div>')


PAGE = (
    '<html><body><div class="tile dolar"><div class="tile is-child">'
    '<a class="titleText" href="/cotizaciondolarblue">Dólar blue</a><div class="values">'
    '<div class="compra"><div class="label">Compra</div><div class="val">$1.540</div></div>'
    '<div class="venta"><div class="label">Venta</div><div class="val">$1.560</div></div></div>'
    '<div class="tile update"><span>Actualizado por última vez: 24/09/26 01:05 PM</span></div></div>'
    # la versión móvil repite el blue con otros valores: vale el primero
    + _block("/cotizaciondolarblue", "Dólar blue", "$9.999", "$9.999")
    + _block("/cotizaciondolaroficial", "Dólar Oficial", "$1.490", "$1.540")
    + _block("/cotizaciondolarbolsa", "Dólar MEP", "$1.539,70", "$1.541,40")
    # el digital linkea al oficial: se reconoce por el nombre
    + _block("/cotizaciondolaroficial", "Dólar Digital (USDC)", "$1.599,38", "$1.606,88",
             extra='<a class="cotizaciones__logo-link" href="https://sponsor"><div>Conseguilo en:</div></a>')
    + "</div></body></html>")


class DolarhoyParserTests(unittest.TestCase):
    def test_amounts_in_argentine_format(self) -> None:
        self.assertEqual(parse_amount("$1.539,70"), 1539.7)
        self.assertEqual(parse_amount("$1.540"), 1540.0)
        self.assertEqual(parse_amount("980,5"), 980.5)

    def test_quotes_by_kind_with_the_mid_price(self) -> None:
        quotes = parse_quotes(PAGE)
        self.assertEqual(set(quotes), {"blue", "oficial", "mep", "digital"})
        self.assertEqual((quotes["blue"].buy, quotes["blue"].sell, quotes["blue"].mid), (1540, 1560, 1550))
        self.assertEqual(quotes["blue"].updated, "24/09/26 01:05 PM")
        self.assertEqual((quotes["oficial"].name, quotes["oficial"].mid), ("Dólar Oficial", 1515))
        self.assertEqual((quotes["digital"].name, quotes["digital"].mid), ("Dólar Digital (USDC)", 1603.13))

    def test_a_page_without_quotes_is_empty(self) -> None:
        self.assertEqual(parse_quotes("<html><body>mantenimiento</body></html>"), {})


class DolarhoyFetchTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_reads_the_home_page(self) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return httpx.Response(200, text=PAGE)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            quotes = await fetch_quotes(client=client)
        self.assertEqual(seen, [DOLARHOY_URL])
        self.assertEqual(quotes["digital"].mid, 1603.13)

    async def test_a_changed_page_is_an_error_not_an_empty_rate(self) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, text="<html></html>"))
        async with httpx.AsyncClient(transport=transport) as client:
            with self.assertRaises(ValueError):
                await fetch_quotes(client=client)


if __name__ == "__main__":
    unittest.main()
