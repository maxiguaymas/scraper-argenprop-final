import unittest

from src.argenprop.urls import (
    Segment,
    direct_listing_url,
    is_valid_listing_url,
    listing_url,
    parse_segment_slug,
)


class TestArgenpropUrls(unittest.TestCase):
    def test_direct_listing_url(self):
        base = "https://www.argenprop.com/inmuebles/alquiler-o-venta/salta-arg"
        self.assertEqual(direct_listing_url(base, 1), base)
        self.assertEqual(direct_listing_url(base, 2), f"{base}?pagina-2")
        self.assertEqual(direct_listing_url(base, 10), f"{base}?pagina-10")

    def test_segment_url(self):
        seg = Segment(tipo="casas", op="venta", loc="salta-arg", kind="plain")
        self.assertEqual(listing_url(seg, 1), "https://www.argenprop.com/casas/venta/salta-arg")
        self.assertEqual(listing_url(seg, 3), "https://www.argenprop.com/casas/venta/salta-arg?pagina-3")

    def test_price_segment_slug(self):
        seg = Segment(
            tipo="departamentos",
            op="alquiler",
            loc="salta",
            kind="price",
            lo=200000,
            hi=400000,
            currency="pesos",
        )
        self.assertEqual(seg.slug, "departamentos-alquiler-salta-200000-400000-pesos")

        parsed = parse_segment_slug(seg.slug)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.tipo, "departamentos")
        self.assertEqual(parsed.op, "alquiler")
        self.assertEqual(parsed.lo, 200000)
        self.assertEqual(parsed.hi, 400000)

    def test_is_valid_listing_url(self):
        self.assertTrue(is_valid_listing_url("https://www.argenprop.com/casa-en-venta-en-salta--123456", "123456"))
        self.assertFalse(is_valid_listing_url("https://www.argenprop.com/-123456", "123456"))
        self.assertFalse(is_valid_listing_url("https://www.argenprop.com/inmobiliarias/remax--123456"))


if __name__ == "__main__":
    unittest.main()
