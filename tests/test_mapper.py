import unittest

from src.db.mapper import to_property_dict


class TestArgenpropMapper(unittest.TestCase):
    def test_mapper_fields(self):
        raw = {
            "argenprop_id": "19720723",
            "titulo": "Hermosa casa en Grand Bourg",
            "tipo_propiedad": "casa",
            "tipo_operacion": "venta",
            "precio": 170000.0,
            "moneda": "USD",
            "superficie_total": 200.0,
            "dormitorios": 3,
            "banos": 2,
            "es_super_destacado": True,
            "visualizaciones": 2300,
            "url": "https://www.argenprop.com/casa-en-venta--19720723",
        }
        res = to_property_dict(raw)
        self.assertEqual(res["argenprop_id"], "19720723")
        self.assertEqual(res["precio"], 170000.0)
        self.assertEqual(res["moneda"], "USD")
        self.assertEqual(res["precio_m2"], 850.0)  # 170000 / 200
        self.assertTrue(res["es_super_destacado"])
        self.assertEqual(res["visualizaciones"], 2300)
        self.assertTrue(res["activa"])


if __name__ == "__main__":
    unittest.main()
