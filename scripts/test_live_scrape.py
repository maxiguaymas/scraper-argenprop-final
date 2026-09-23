"""
Script de prueba rápida en vivo:
Descarga la primera página del link de Salta y muestra las propiedades en consola sin requerir base de datos.
Ejecutar:
    python scripts/test_live_scrape.py
"""

import asyncio
from src.argenprop.parser import extract_total_from_html, parse_listings_html
from src.argenprop.session import ApSession

URL = "https://www.argenprop.com/inmuebles/alquiler-o-venta/salta-arg"


async def main():
    print(f"\n🔍 Conectando a Argenprop: {URL} ...")
    session = ApSession()
    try:
        await session.init()
        html = await session.get_html(URL)
        if not html:
            print("❌ No se pudo obtener respuesta (posible bloqueo WAF).")
            return

        total = extract_total_from_html(html)
        print(f"📊 Total de avisos en la provincia de Salta: {total}")

        listings = parse_listings_html(html, pagina_origen=1)
        print(f"✅ Propiedades parseadas en página 1: {len(listings)}\n")

        print("=" * 80)
        for i, p in enumerate(listings[:5], 1):
            precio_fmt = f"{p['moneda']} {p['precio']:,.0f}" if p['precio'] else "Consultar precio"
            exp_fmt = f" (+ ${p['expensas']:,.0f} exp)" if p['expensas'] else ""
            super_tag = " [⭐ SÚPER DESTACADO]" if p['es_super_destacado'] else ""
            print(f"#{i} {p['titulo'] or p['direccion']}{super_tag}")
            print(f"   💰 Precio: {precio_fmt}{exp_fmt}")
            print(f"   🏠 Tipo: {p['tipo_propiedad']} | Operación: {p['tipo_operacion']}")
            print(f"   📐 Sup: {p['superficie_total']} m² | Dorms: {p['dormitorios']} | Baños: {p['banos']}")
            print(f"   👁️  Visto / Puntos: {p['visualizaciones']}")
            print(f"   🔗 URL: {p['url']}")
            print("-" * 80)

        print("\n🎉 ¡Prueba completada con éxito!")
    finally:
        await session.close()


if __name__ == "__main__":
    asyncio.run(main())
