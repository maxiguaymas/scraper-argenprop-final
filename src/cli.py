from __future__ import annotations

import asyncio
from typing import Optional

import typer

from src.db.engine import async_session_factory
from src.db.repository import get_stats
from src.services.scheduler import start_scheduler_blocking
from src.services.sync import run_enrich, run_sync

cli = typer.Typer(help="Argenprop Scraper CLI — Salta & NOA")


@cli.command()
def scrape(
    url: Optional[str] = typer.Option(
        None,
        "--url",
        "-u",
        help="URL específica de Argenprop a scrapear (por defecto: Salta catálogo completo)",
    ),
    limit: int = typer.Option(100, "--limit", "-l", help="Cantidad máxima de propiedades a obtener"),
    segmented: bool = typer.Option(
        False,
        "--segmented",
        "-s",
        help="Usar modo catálogo segmentado para superar el tope de 10 páginas",
    ),
    enrich: bool = typer.Option(
        True,
        "--enrich/--no-enrich",
        help="Ejecutar enriquecimiento de GPS y teléfono tras el scrape",
    ),
):
    """Ejecuta el scraping y guarda los avisos en la base de datos local."""
    asyncio.run(run_sync(url=url, limit=limit, segmented=segmented, auto_enrich=enrich))


@cli.command()
def enrich(
    limit: int = typer.Option(50, "--limit", "-l", help="Cantidad máxima de fichas a enriquecer"),
):
    """Enriquece propiedades existentes completando datos faltantes (GPS y teléfono)."""
    asyncio.run(run_enrich(limit=limit))


@cli.command()
def stats():
    """Muestra estadísticas del total de propiedades en la base de datos."""
    async def _show_stats():
        async with async_session_factory() as session:
            s = await get_stats(session)
            print("\n📊 Estadísticas de Argenprop en Base de Datos:")
            print(f"  • Activas:   {s['active']}")
            print(f"  • Inactivas: {s['inactive']}")
            print(f"  • Total:     {s['total']}\n")

    asyncio.run(_show_stats())


@cli.command("scrape-supabase")
def scrape_supabase(
    url: Optional[str] = typer.Option(None, "--url", "-u", help="URL específica de Argenprop"),
    limit: int = typer.Option(100, "--limit", "-l", help="Cantidad máxima de propiedades a sincronizar"),
    segmented: bool = typer.Option(False, "--segmented", "-s", help="Usar modo segmentado"),
    enrich: bool = typer.Option(True, "--enrich/--no-enrich", help="Enriquecer con datos de API"),
):
    """Scrapea y sincroniza directamente contra la tabla Supabase argenprop_propiedades (CRM)."""
    from src.services.supabase_sync import run_supabase_scrape

    outcome = asyncio.run(run_supabase_scrape(url=url, limit=limit, segmented=segmented, auto_enrich=enrich))
    raise SystemExit(0 if outcome.get("ok") else 1)


@cli.command("push-local-to-supabase")
def push_to_supabase():
    """Copia todas las propiedades de la base de datos local hacia Supabase argenprop_propiedades."""
    from src.services.supabase_sync import push_local_to_supabase

    outcome = asyncio.run(push_local_to_supabase())
    raise SystemExit(0 if outcome.get("ok") else 1)


@cli.command("enrich-supabase")
def enrich_supabase(
    limit: int = typer.Option(50, "--limit", "-l", help="Cantidad máxima de fichas a enriquecer en Supabase"),
):
    """Enriquece en Supabase propiedades que no tengan GPS o teléfono."""
    from src.services.supabase_sync import run_supabase_enrich

    outcome = asyncio.run(run_supabase_enrich(limit=limit))
    raise SystemExit(0 if outcome.get("ok") else 1)


@cli.command("cross-match")
def cross_match(
    limit: int = typer.Option(100, "--limit", "-l", help="Cantidad máxima de propiedades de Argenprop a cruzar"),
):
    """Ejecuta el cruce de mercado entre Argenprop y Zonaprop en Supabase."""
    from src.services.cross_matcher import analyze_cross_market

    res = analyze_cross_market(limit_ap=limit)
    print("\n" + "=" * 55)
    print("📊 REPORTE DE MERCADO CRUZADO: ARGENPROP VS ZONAPROP")
    print("=" * 55)
    print(f"  • Propiedades de Argenprop analizadas: {res['total_argenprop']}")
    print(f"  • Base de Zonaprop comparada:          {res['total_zonaprop_analizadas']}")
    print(f"  ⭐ OPORTUNIDADES EXCLUSIVAS ARGENPROP: {res['exclusivas_argenprop_count']} ({res['porcentaje_exclusividad_argenprop']}%)")
    print(f"  🔄 Coincidentes en ambos portales:     {res['compartidas_count']}")
    print("=" * 55)

    if res["compartidas"]:
        print(f"\nEjemplos de propiedades compartidas ({len(res['compartidas'])} encontradas):")
        for idx, c in enumerate(res["compartidas"][:3]):
            ap = c["argenprop"]
            zp = c["zonaprop"]
            print(f"  [{idx+1}] Score: {c['score']} pts")
            print(f"      Argenprop #{ap['argenprop_id']}: {ap['titulo'][:40]} ({ap['moneda']} {ap.get('precio', 0):,.0f})")
            print(f"      Zonaprop  #{zp['zonaprop_id']}: {zp['titulo'][:40]} ({zp['moneda']} {zp.get('precio', 0):,.0f})")
            print(f"      Coincidencias: {', '.join(c['reasons'])}")
    print("")


@cli.command("sync-all")
def sync_all(
    limit: int = typer.Option(100, "--limit", "-l", help="Cantidad de propiedades a scrapear y procesar"),
    segmented: bool = typer.Option(False, "--segmented", "-s", help="Usar modo segmentado"),
    cross: bool = typer.Option(True, "--cross/--no-cross", help="Ejecutar cruce contra Zonaprop al terminar"),
):
    """Ejecuta el pipeline COMPLETO en 1 solo comando:
    1. Scrapea Argenprop
    2. Enriquece con GPS, teléfonos reales y fotos HD
    3. Guarda localmente y sincroniza en Supabase
    4. Cruza contra Zonaprop y muestra las exclusividades
    """
    async def _pipeline():
        print("\n" + "🔥" * 25)
        print("🚀 INICIANDO PIPELINE MAESTRO DE ARGENPROP")
        print("🔥" * 25)

        # Paso 1 & 2: Scrape + Enrich local
        print("\n[Paso 1/3] Scrapeando catálogo y enriqueciendo fichas...")
        await run_sync(limit=limit, segmented=segmented, auto_enrich=True)

        # Paso 3: Subida a Supabase
        print("\n[Paso 2/4] Sincronizando con Supabase (argenprop_propiedades)...")
        from src.services.supabase_sync import push_local_to_supabase, run_supabase_enrich
        await push_local_to_supabase()

        # Paso 3: Enriquecimiento en Supabase (GPS + Teléfonos reales)
        print("\n[Paso 3/4] Enriqueciendo en Supabase con GPS y teléfonos reales...")
        await run_supabase_enrich(limit=limit)

        # Paso 4: Cruce de mercado
        if cross:
            print("\n[Paso 4/4] Ejecutando cruce de mercado con Zonaprop...")
            from src.services.cross_matcher import analyze_cross_market
            res = analyze_cross_market(limit_ap=limit)
            print("\n" + "=" * 55)
            print("📊 RESULTADOS FINALES DEL CRUCE CON ZONAPROP")
            print("=" * 55)
            print(f"  • Propiedades Argenprop:         {res['total_argenprop']}")
            print(f"  ⭐ OPORTUNIDADES SOLO EN ARGENPROP: {res['exclusivas_argenprop_count']} ({res['porcentaje_exclusividad_argenprop']}%)")
            print(f"  🔄 Coincidentes en ambos portales: {res['compartidas_count']}")
            print("=" * 55 + "\n")

    asyncio.run(_pipeline())


@cli.command("pipeline")
def pipeline_cmd(
    limit: int = typer.Option(10000, "--limit", "-l", help="Límite máximo de propiedades a scrapear"),
    enrich_limit: int = typer.Option(300, "--enrich-limit", help="Límite de fichas a enriquecer"),
    verify_bajas: bool = typer.Option(True, "--verify-bajas/--no-verify-bajas", help="Doble check de fichas dadas de baja"),
):
    """Ejecuta el pipeline de producción completo (Scrape -> DB -> Bajas -> Enrich -> Cross-Match)."""
    from src.services.supabase_sync import run_full_production_pipeline

    outcome = asyncio.run(run_full_production_pipeline(limit=limit, enrich_limit=enrich_limit, verify_bajas=verify_bajas))
    raise SystemExit(0 if outcome.get("status") == "success" else 1)


@cli.command("persist-match")
def persist_match_cmd():
    """Ejecuta el cruce de mercado Argenprop vs Zonaprop y persiste los flags en Supabase."""
    from src.services.cross_matcher import persist_cross_matches_to_supabase

    res = persist_cross_matches_to_supabase()
    raise SystemExit(0 if res.get("ok") else 1)


@cli.command()
def schedule():
    """Inicia el scheduler en primer plano para sincronizaciones automáticas cada 2 horas."""
    asyncio.run(start_scheduler_blocking())


if __name__ == "__main__":
    cli()
