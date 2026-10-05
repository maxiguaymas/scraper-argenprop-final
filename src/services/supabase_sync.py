from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select

from src.argenprop.detail_enricher import enrich_single_listing
from src.argenprop.region import get_region, use_region
from src.argenprop.scraper import scrape_catalog_segmented, scrape_direct_url
from src.argenprop.session import ApSession
from src.config import settings
from src.db.engine import async_session_factory
from src.db.mapper import to_supabase_record
from src.db.models import ArgenpropProperty
from src.db.supabase_client import count_active, get_missing_enrich_supabase, update_property
from src.db.supabase_repository import save_batch_supabase, save_to_supabase


async def push_local_to_supabase() -> dict[str, Any]:
    """Copia todas las propiedades de la base de datos local hacia Supabase argenprop_propiedades."""
    print("\n🚀 Sincronizando propiedades locales hacia Supabase...")
    async with async_session_factory() as session:
        res = await session.execute(
            select(ArgenpropProperty).where(ArgenpropProperty.activa.is_(True))
        )
        props = res.scalars().all()

    if not props:
        print("  ⚠️ No hay propiedades en la base de datos local.")
        return {"ok": False, "count": 0}

    print(f"  📦 Cargando {len(props)} propiedades locales...")
    prop_dicts = []
    for p in props:
        d = {c.name: getattr(p, c.name) for c in p.__table__.columns}
        prop_dicts.append(d)

    results = save_batch_supabase(prop_dicts)
    active_in_sb = count_active()
    print(
        f"  ✅ Resultado Supabase: {results['inserted']} insertadas, "
        f"{results['updated']} actualizadas, {results['errors']} errores."
    )
    print(f"  📊 Total activas en Supabase argenprop_propiedades: {active_in_sb}\n")
    return {
        "ok": results["errors"] == 0,
        "local_count": len(props),
        "results": results,
        "active_in_supabase": active_in_sb,
    }


async def run_supabase_enrich(limit: int = 50, region: str = "salta") -> dict[str, Any]:
    """Enriquece propiedades directamente en Supabase que no tengan GPS o teléfono."""
    with use_region(region) as cfg:
        print(f"\n🔍 Buscando propiedades pendientes de enriquecer en Supabase [{cfg.provincia}] (límite: {limit})...")
        missing = get_missing_enrich_supabase(limit=limit)
        if not missing:
            print(f"  ℹ️ Todas las propiedades en Supabase ({cfg.table}) ya están enriquecidas.")
            return {"ok": True, "attempted": 0, "enriched": 0}

        print(f"  🔎 Enriqueciendo {len(missing)} propiedades en Supabase [{cfg.table}]...")
        session = ApSession()
        stats = {"attempted": 0, "enriched": 0, "errors": 0}

        try:
            await session.init()
            now = datetime.now(UTC)
            sem = asyncio.Semaphore(10)

            async def _enrich_one(item):
                aid = item["argenprop_id"]
                url = item.get("url")
                row_id = item["id"]
                async with sem:
                    stats["attempted"] += 1
                    try:
                        fields = await enrich_single_listing(session, url, aid)
                        if fields:
                            fields["argenprop_id"] = aid
                            rec = to_supabase_record(fields, now=now, is_insert=False)
                            await asyncio.to_thread(update_property, row_id, rec)
                            stats["enriched"] += 1
                    except Exception as exc:
                        print(f"  ⚠️ Error actualizando {aid} en Supabase: {exc}")
                        stats["errors"] += 1
                    await asyncio.sleep(0.05)

            # Procesar en bloques concurrentes
            chunk_size = 50
            for i in range(0, len(missing), chunk_size):
                chunk = missing[i:i + chunk_size]
                await asyncio.gather(*[_enrich_one(item) for item in chunk])
                print(f"  ...enriquecidas {stats['enriched']}/{len(missing)}")
        finally:
            await session.close()

        print(
            f"  ✅ Enriquecimiento Supabase [{cfg.provincia}] finalizado: {stats['enriched']} enriquecidas, "
            f"{stats['errors']} errores de {stats['attempted']} procesadas."
        )
        return {"ok": stats["errors"] == 0, **stats}


async def run_supabase_scrape(
    url: str | None = None,
    limit: int = 100,
    segmented: bool = False,
    auto_enrich: bool = True,
    region: str = "salta",
) -> dict[str, Any]:
    """Scrapea Argenprop y persiste directamente en Supabase según la región activa."""
    with use_region(region) as cfg:
        target_url = url or (
            f"https://www.argenprop.com/inmuebles/alquiler-o-venta/{cfg.loc}"
            if url is None and cfg.key != "salta"
            else (url or settings.argenprop_start_url)
        )
        start_time = datetime.now(UTC)
        print(f"\n[{start_time:%Y-%m-%d %H:%M:%S} UTC] 🚀 Iniciando scrape hacia Supabase [{cfg.provincia} -> {cfg.table}]...")

        session = ApSession()
        listings: list[dict[str, Any]] = []

        try:
            await session.init()
            if segmented:
                res = await scrape_catalog_segmented(session=session, limit=limit)
            else:
                res = await scrape_direct_url(target_url, session=session, limit=limit)
            listings = res.get("listings") or []

            if auto_enrich and listings:
                print(f"  🔍 Enriqueciendo automáticamente {len(listings)} propiedades con datos de API...")
                for item in listings:
                    aid = item.get("argenprop_id")
                    u = item.get("url")
                    if aid and u:
                        fields = await enrich_single_listing(session, u, aid)
                        if fields:
                            item.update(fields)
                    await asyncio.sleep(0.2)
        finally:
            await session.close()

        print(f"  📦 Propiedades obtenidas: {len(listings)}")
        if not listings:
            return {"ok": False, "error": "no_listings"}

        results = save_batch_supabase(listings)
        print(
            f"  Guardado Supabase [{cfg.table}] -> insertadas={results['inserted']}, "
            f"actualizadas={results['updated']}, errores={results['errors']}"
        )

        active_count = count_active()
        print(f"  Total activas en Supabase [{cfg.table}]: {active_count}")

        return {
            "ok": results["errors"] == 0,
            "region": cfg.key,
            "table": cfg.table,
            "scraped": len(listings),
            "results": results,
            "active_in_supabase": active_count,
        }


async def run_full_production_pipeline(
    limit: int = 10000,
    enrich_limit: int = 1000,
    verify_bajas: bool = True,
    region: str = "salta",
) -> dict[str, Any]:
    """
    Pipeline de producción completo ejecutado periódicamente en Railway:
    1. Scrape del catálogo segmentado según región (sin tope artificial de inventario).
    2. Guardado masivo y actualización en Supabase (UPSERT a tabla de región).
    3. Detección y doble-check de avisos dados de baja (activa = false).
    4. Enriquecimiento de fichas nuevas (GPS exacto, teléfono/WA, fotos HD).
    5. Cruce inteligente contra Zonaprop y persistencia en Supabase.
    """
    from src.argenprop.ficha_status import verify_ficha_urls
    from src.db.supabase_client import get_all_active_ids, mark_delisted_batch
    from src.services.cross_matcher import persist_cross_matches_to_supabase

    with use_region(region) as cfg:
        start_time = datetime.now(UTC)
        print(f"\n{'='*70}")
        print(f"🚀 [{start_time:%Y-%m-%d %H:%M:%S} UTC] INICIANDO PIPELINE: {cfg.provincia.upper()} ({cfg.table})")
        print(f"{'='*70}\n")

        summary: dict[str, Any] = {
            "region": cfg.key,
            "provincia": cfg.provincia,
            "table": cfg.table,
            "started_at": start_time.isoformat(),
            "finished_at": None,
            "status": "running",
            "scrape": {},
            "delisted": {},
            "enrich": {},
            "cross_match": {},
        }

        # FASE 1: Scrape de Catálogo Segmentado
        print(f"📍 [FASE 1/5] Scrapeando catálogo Argenprop {cfg.provincia} ({cfg.loc})...")
        session = ApSession()
        scraped_listings: list[dict[str, Any]] = []
        try:
            await session.init()
            res_scrape = await scrape_catalog_segmented(session=session, limit=limit)
            scraped_listings = res_scrape.get("listings") or []
        finally:
            await session.close()

        print(f"  📦 Catálogo obtenido [{cfg.provincia}]: {len(scraped_listings)} avisos activos.")
        summary["scrape"]["obtained"] = len(scraped_listings)

        if not scraped_listings:
            print(f"  ⚠️ No se obtuvieron avisos del catálogo de {cfg.provincia}. Abortando fases posteriores.")
            summary["status"] = "aborted_no_listings"
            summary["finished_at"] = datetime.now(UTC).isoformat()
            return summary

        # FASE 2: Upsert masivo a Supabase
        print(f"\n📍 [FASE 2/5] Guardando catálogo en Supabase ({cfg.table})...")
        save_res = save_batch_supabase(scraped_listings)
        summary["scrape"]["save_results"] = save_res
        print(f"  ✅ Guardado [{cfg.table}]: {save_res['updated']} actualizadas/insertadas, {save_res['errors']} errores.")

        # FASE 3: Detección y Doble-Check de Bajas
        print(f"\n📍 [FASE 3/5] Verificando avisos despublicados en {cfg.provincia} (bajas)...")
        scraped_ids = {str(item.get("argenprop_id")) for item in scraped_listings if item.get("argenprop_id")}

        # Umbral de seguridad para bajas: Salta > 1000, Jujuy > 80 (Jujuy tiene inventario total menor)
        min_threshold = 80 if cfg.key == "jujuy" else 1000
        if len(scraped_ids) >= min_threshold:
            active_in_db = await asyncio.to_thread(get_all_active_ids)
            suspected_delisted = [
                p for p in active_in_db
                if str(p.get("argenprop_id")) not in scraped_ids and p.get("url")
            ]
            print(f"  🔍 Avisos en DB que no figuraron en el catálogo actual: {len(suspected_delisted)}")

            confirmed_bajas_ids: list[str] = []
            if suspected_delisted:
                if verify_bajas:
                    max_check = min(len(suspected_delisted), 500)
                    print(f"  🕵️ Ejecutando doble-check HTTP en {max_check} fichas sospechosas...")
                    items_to_check = [{"zpId": str(p["argenprop_id"]), "url": p.get("url") or ""} for p in suspected_delisted[:max_check]]
                    check_results = await verify_ficha_urls(items_to_check, concurrency=4)
                    for r in check_results:
                        if not r.get("alive"):
                            confirmed_bajas_ids.append(str(r["zpId"]))
                    print(f"  🎯 Bajas confirmadas por 410/404: {len(confirmed_bajas_ids)}")
                else:
                    confirmed_bajas_ids = [str(p["argenprop_id"]) for p in suspected_delisted]

            if confirmed_bajas_ids:
                updated_bajas = await asyncio.to_thread(
                    mark_delisted_batch, confirmed_bajas_ids, "removida_http_410"
                )
                summary["delisted"]["confirmed"] = updated_bajas
                print(f"  ✅ {updated_bajas} propiedades marcadas como inactivas (activa=false).")
            else:
                summary["delisted"]["confirmed"] = 0
                print("  ℹ️ No se detectaron bajas confirmadas.")
        else:
            print(f"  ⚠️ El volumen scrapeado ({len(scraped_ids)}) fue inferior al umbral ({min_threshold}). Se omitió chequeo de bajas.")
            summary["delisted"]["skipped"] = True

        # FASE 4: Enriquecimiento de Fichas Nuevas / Faltantes
        print(f"\n📍 [FASE 4/5] Enriqueciendo propiedades nuevas o sin GPS/teléfono [{cfg.provincia}]...")
        enrich_res = await run_supabase_enrich(limit=enrich_limit, region=cfg.key)
        summary["enrich"] = enrich_res

        # FASE 5: Cruce Inteligente Argenprop vs Zonaprop y Persistencia
        print(f"\n📍 [FASE 5/5] Ejecutando cruce inteligente {cfg.provincia} Argenprop vs Zonaprop...")
        match_res = await asyncio.to_thread(persist_cross_matches_to_supabase)
        summary["cross_match"] = match_res

        finish_time = datetime.now(UTC)
        duration = (finish_time - start_time).total_seconds()
        summary["finished_at"] = finish_time.isoformat()
        summary["duration_seconds"] = round(duration, 1)
        summary["status"] = "success"

        print(f"\n{'='*70}")
        print(f"🎉 PIPELINE {cfg.provincia.upper()} COMPLETADO EXITOSAMENTE en {duration:.1f} segundos")
        print(f"   • Propiedades catálogo: {summary['scrape']['obtained']}")
        print(f"   • Fichas enriquecidas: {enrich_res.get('enriched', 0)}")
        print(f"   • Compartidas con Zonaprop: {match_res.get('compartidas', 0)}")
        print(f"   • Exclusivas Argenprop: {match_res.get('exclusivas', 0)} ({match_res.get('porcentaje_exclusividad', 0)}%)")
        print(f"{'='*70}\n")

        return summary


async def run_all_regions_pipeline(
    limit: int = 10000,
    enrich_limit: int = 1000,
    verify_bajas: bool = True,
) -> dict[str, Any]:
    """Ejecuta secuencialmente el pipeline de producción para todas las regiones (Salta y Jujuy)."""
    start_time = datetime.now(UTC)
    results = {}
    for r in ["salta", "jujuy"]:
        print(f"\n🌍 ====================================================================")
        print(f"🌍 >>> INICIANDO PROCESO COMPLETO REGION: {r.upper()} <<<")
        print(f"🌍 ====================================================================")
        try:
            res = await run_full_production_pipeline(
                limit=limit,
                enrich_limit=enrich_limit,
                verify_bajas=verify_bajas,
                region=r,
            )
            results[r] = res
        except Exception as exc:
            print(f"❌ Error en pipeline de región {r}: {exc}")
            results[r] = {"status": "error", "error": str(exc)}

    finish_time = datetime.now(UTC)
    duration = (finish_time - start_time).total_seconds()
    return {
        "status": "success",
        "started_at": start_time.isoformat(),
        "finished_at": finish_time.isoformat(),
        "total_duration_seconds": round(duration, 1),
        "regions": results,
    }
