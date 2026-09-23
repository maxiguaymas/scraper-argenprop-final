from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from src.argenprop.detail_enricher import enrich_single_listing
from src.argenprop.scraper import scrape_catalog_segmented, scrape_direct_url
from src.argenprop.session import ApSession
from src.config import settings
from src.db.engine import async_session_factory
from src.db.repository import (
    get_missing_enrich,
    get_stats,
    mark_inactive_before,
    update_enriched,
    upsert_property,
)

BATCH_SIZE = 50


async def run_sync(
    url: str | None = None,
    limit: int = 200,
    segmented: bool = False,
    auto_enrich: bool = True,
) -> dict[str, Any]:
    target_url = url or settings.argenprop_start_url
    start_time = datetime.now(UTC)
    print(f"\n[{start_time:%Y-%m-%d %H:%M:%S} UTC] 🚀 Iniciando sync de Argenprop...")

    session = ApSession()
    listings: list[dict[str, Any]] = []

    try:
        await session.init()
        if segmented:
            res = await scrape_catalog_segmented(session=session, limit=limit)
        else:
            res = await scrape_direct_url(target_url, session=session, limit=limit)
        listings = res.get("listings") or []
    finally:
        await session.close()

    print(f"  📦 Propiedades obtenidas: {len(listings)}")
    if not listings:
        print("  ⚠️ No se obtuvieron avisos para guardar.")
        return {"inserted": 0, "listings": 0}

    inserted = 0
    async with async_session_factory() as db_session:
        for i, item in enumerate(listings):
            await upsert_property(db_session, item, scrape_time=start_time)
            inserted += 1
            if inserted % BATCH_SIZE == 0:
                await db_session.commit()
                print(f"  ...guardadas {inserted}/{len(listings)}")
        await db_session.commit()

        # Si fue un scrape segmentado masivo, se pueden marcar inactivas las no vistas
        removed = 0
        if segmented and len(listings) >= 300:
            removed = await mark_inactive_before(db_session, start_time)
            await db_session.commit()
            print(f"  Marcadas inactivas: {removed}")

        stats = await get_stats(db_session)

    print(f"  ✅ Guardadas en DB: {inserted}")
    print(f"  📊 Totales en DB: {stats['active']} activas | {stats['inactive']} inactivas | {stats['total']} total")

    if auto_enrich and inserted > 0:
        print("\n  🔍 Iniciando enriquecimiento automático de fichas (GPS y teléfono)...")
        await run_enrich(limit=min(inserted, 30))

    end_time = datetime.now(UTC)
    elapsed = (end_time - start_time).total_seconds()
    print(f"[{end_time:%Y-%m-%d %H:%M:%S} UTC] 🎉 Sync completado en {elapsed:.1f}s.\n")
    return {"inserted": inserted, "stats": stats}


async def run_enrich(limit: int = 50) -> dict[str, int]:
    """Recorre avisos sin lat/lon o teléfono y descarga su ficha para enriquecer."""
    now = datetime.now(UTC)
    async with async_session_factory() as db_session:
        missing = await get_missing_enrich(db_session, limit=limit)

    if not missing:
        print("  ℹ️ No hay propiedades pendientes de enriquecer.")
        return {"attempted": 0, "enriched": 0}

    print(f"  🔎 Enriqueciendo {len(missing)} propiedades...")
    session = ApSession()
    stats = {"attempted": 0, "enriched_coords": 0, "enriched_phone": 0, "enriched_images": 0}

    consecutive_fails = 0
    try:
        await session.init()
        async with async_session_factory() as db_session:
            for item in missing:
                aid = item["argenprop_id"]
                url = item["url"]
                if not url:
                    continue

                stats["attempted"] += 1
                fields = await enrich_single_listing(
                    session,
                    url,
                    aid,
                    referer=settings.argenprop_start_url,
                )
                if session.waf_blocked:
                    consecutive_fails += 1
                    print(f"  ⚠️ Ficha {aid} con aviso WAF ({consecutive_fails}/3) — rotando fingerprint...")
                    await session._rotate_fingerprint()
                    session.reset_waf_status()
                    await asyncio.sleep(2.0)
                    if consecutive_fails >= 3:
                        print("  ⛔ 3 avisos WAF consecutivos — pausando enriquecimiento.")
                        break
                    continue

                consecutive_fails = 0
                if fields:
                    if "latitud" in fields:
                        stats["enriched_coords"] += 1
                    if "anunciante_telefono" in fields:
                        stats["enriched_phone"] += 1
                    if "imagenes" in fields and len(fields["imagenes"]) > 1:
                        stats["enriched_images"] += 1
                    await update_enriched(db_session, aid, fields, now)
                    await db_session.commit()

                await asyncio.sleep(1.2)
    finally:
        await session.close()

    print(
        f"  Enriquecimiento finalizado: {stats['attempted']} procesadas, "
        f"{stats['enriched_coords']} con GPS, {stats['enriched_phone']} con teléfono, "
        f"{stats['enriched_images']} con galería HD."
    )
    return stats
