from pathlib import Path
import unittest

from src.argenprop.parser import (
    extract_total_from_html,
    parse_ar_float,
    parse_ar_int,
    parse_listings_html,
)
from src.argenprop.detail_enricher import extract_detail_fields, extract_map_coords

FIXTURE_LISTING = Path(__file__).parent / "fixtures" / "argenprop_listing.html"
FIXTURE_DETAIL = Path(__file__).parent / "fixtures" / "argenprop_detail.html"


class TestArgenpropParser(unittest.TestCase):
    def test_parse_ar_int(self):
        self.assertEqual(parse_ar_int("2.300"), 2300)
        self.assertEqual(parse_ar_int("752"), 752)
        self.assertEqual(parse_ar_int("1.875"), 1875)

    def test_parse_ar_float(self):
        self.assertEqual(parse_ar_float("170.000"), 170000.0)
        self.assertEqual(parse_ar_float("660000"), 660000.0)
        self.assertEqual(parse_ar_float("125.000"), 125000.0)

    def test_parse_listing_fixture(self):
        html = FIXTURE_LISTING.read_text(encoding="utf-8")
        total = extract_total_from_html(html)
        self.assertEqual(total, 668)

        listings = parse_listings_html(html, pagina_origen=1, tipo_hint="casa", op_hint="venta")
        self.assertEqual(len(listings), 3)

        by_id = {x["argenprop_id"]: x for x in listings}

        # Aviso super destacado
        a = by_id["19720723"]
        self.assertEqual(a["precio"], 170000.0)
        self.assertEqual(a["moneda"], "USD")
        self.assertEqual(a["dormitorios"], 2)
        self.assertEqual(a["banos"], 3)
        self.assertEqual(a["visualizaciones"], 2300)
        self.assertTrue(a["es_super_destacado"])
        self.assertIn("--19720723", a["url"])

        # Aviso con expensas
        b = by_id["19391940"]
        self.assertEqual(b["precio"], 125000.0)
        self.assertEqual(b["expensas"], 450000.0)
        self.assertEqual(b["visualizaciones"], 752)

        # Aviso sin precio ("Consultar precio")
        c = by_id["19218853"]
        self.assertIsNone(c["precio"])
        self.assertEqual(c["visualizaciones"], 1875)

    def test_extract_detail_fields(self):
        if not FIXTURE_DETAIL.exists():
            return
        html = FIXTURE_DETAIL.read_text(encoding="utf-8")
        fields = extract_detail_fields(html)
        if "latitud" in fields:
            self.assertGreater(fields["latitud"], -56.0)
            self.assertLess(fields["latitud"], -21.0)


if __name__ == "__main__":
    unittest.main()
