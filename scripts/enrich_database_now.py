#!/usr/bin/env python3
"""
Script de enriquecimiento masivo ultra-rápido:
Consulta la API interna de Argenprop (sosiva451) para cada propiedad en Supabase
y completa:
- Coordenadas GPS exactas (latitud, longitud)
- Teléfono y WhatsApp directo (+549...)
- Galería completa de fotos HD
- Descripción completa
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
import re
import sys
import time
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.argenprop.detail_enricher import extract_fields_from_api_json
from src.argenprop.session import ApSession
from src.db import supabase_client as sb
from src.db.mapper import to_supabase_record
from src.services.cross_matcher import fetch_supabase_table

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("enricher")


async def enrich_batch(
    session: ApSession,
    items: list[dict[str, Any]],
    concurrency: int = 15,
) -> tuple[int, int, int]:
    sem = asyncio.Semaphore(concurrency)
    now = datetime.now(timezone.utc)
    enriched_records: list[tuple[int, dict[str, Any]]] = []
    success = 0
    no_data = 0
    errors = 0

    async def _fetch_one(item: dict[str, Any]):
        nonlocal success, no_data, errors
        aid = str(item.get("argenprop_id") or "")
        row_id = item.get("id")
        if not aid or not row_id:
            return

        async with sem:
            try:
                data = await session.get_json(f"https://api.sosiva451.com/Avisos/{aid}")
                if data and isinstance(data, dict) and data.get("IdAviso"):
                    fields = extract_fields_from_api_json(data)
                    fields["argenprop_id"] = aid
                    rec = to_supabase_record(fields, now=now, is_insert=False)
                    enriched_records.append((row_id, rec))
                    success += 1
                else:
                    rec = to_supabase_record(
                        {"argenprop_id": aid, "coordenadas_origen": "sin_datos"},
                        now=now,
                        is_insert=False,
                    )
                    enriched_records.append((row_id, rec))
                    no_data += 1
            except Exception as exc:
                errors += 1
            await asyncio.sleep(0.02)

    await asyncio.gather(*[_fetch_one(it) for it in items])

    # Guardar en Supabase en paralelo
    save_sem = asyncio.Semaphore(10)

    async def _save_one(row_id: int, rec: dict[str, Any]):
        async with save_sem:
            try:
                await asyncio.to_thread(sb.update_property, row_id, rec)
            except Exception as exc:
                logger.warning("Error guardando propiedad %s: %s", row_id, exc)

    await asyncio.gather(*[_save_one(rid, r) for rid, r in enriched_records])
    return success, no_data, errors


async def run_full_enrichment(limit_total: int | None = None, batch_size: int = 200):
    print("=" * 70)
    print("🚀 INICIANDO ENRIQUECIMIENTO MASIVO DE ARGENPROP (GPS, TELÉFONO, WA, FOTOS)")
    print("=" * 70)

    # Buscar propiedades que no tengan coordenadas_origen o no tengan teléfono
    print("📥 Descargando propiedades pendientes de enriquecer...")
    filter_query = "coordenadas_origen=is.null&activa=eq.true"
    props = fetch_supabase_table(
        "argenprop_propiedades",
        select="id,argenprop_id,url,titulo",
        filter_params=filter_query,
        max_total=limit_total,
    )
    total = len(props)
    print(f"📦 Total propiedades a enriquecer: {total}\n")

    if not props:
        print("✅ Todas las propiedades ya están enriquecidas.")
        return

    session = ApSession()
    await session.init()

    start_time = time.time()
    total_success = 0
    total_no_data = 0
    total_errors = 0

    try:
        for i in range(0, total, batch_size):
            chunk = props[i : i + batch_size]
            c_start = time.time()
            succ, nodata, errs = await enrich_batch(session, chunk, concurrency=15)
            total_success += succ
            total_no_data += nodata
            total_errors += errs
            elapsed = time.time() - c_start
            processed = min(i + batch_size, total)
            print(
                f"  [{processed:4d}/{total}] Enriquecidas: +{succ} (Total OK: {total_success}) "
                f"en {elapsed:.1f}s ({len(chunk)/max(0.1, elapsed):.1f} props/s)"
            )
    finally:
        await session.close()

    total_time = time.time() - start_time
    print("\n" + "=" * 70)
    print(f"🎉 ENRIQUECIMIENTO COMPLETADO EN {total_time:.1f} SEGUNDOS")
    print(f"   • Propiedades enriquecidas con datos: {total_success}")
    print(f"   • Propiedades sin datos en API:       {total_no_data}")
    print(f"   • Errores de red:                     {total_errors}")
    print("=" * 70)


if __name__ == "__main__":
    max_items = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(run_full_enrichment(limit_total=max_items))
