#!/usr/bin/env python3
"""
Auditor de Bajas de Argenprop (Remax NOA)
========================================
Script independiente de auditoría y control de despublicaciones / bajas.
Permite auditar el 100% de las propiedades activas e inactivas en Supabase
contra Argenprop en vivo de forma concurrente y segura contra WAF.

Uso:
  python scripts/audit_bajas.py --all --fix         # Audita TODAS las propiedades activas y da de baja en Supabase las despublicadas
  python scripts/audit_bajas.py --all               # Audita TODAS las activas (solo reporte, sin modificar la DB)
  python scripts/audit_bajas.py --only-inactivas    # Audita todas las propiedades que figuran dadas de baja
  python scripts/audit_bajas.py --sample-activas 50 # Audita una muestra de 50 activas
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any


# Asegurar import de módulos src independientemente del directorio de ejecución
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from curl_cffi import requests

from src.db.supabase_client import (
    _request,
    _require_credentials,
    mark_delisted_batch,
    update_property,
)


def get_inactive_properties(limit: int = 1000) -> list[dict[str, Any]]:
    """Obtiene propiedades marcadas como inactivas en Supabase."""
    return _request(
        "GET",
        "argenprop_propiedades",
        params={
            "activa": "eq.false",
            "select": "id,argenprop_id,titulo,url,precio,moneda,anunciante_nombre,fecha_baja,motivo_baja",
            "limit": str(limit),
            "order": "fecha_baja.desc.nullslast",
        },
    ) or []


def get_active_properties_sample(limit: int = 20) -> list[dict[str, Any]]:
    """Obtiene una muestra de propiedades actualmente activas en Supabase."""
    return _request(
        "GET",
        "argenprop_propiedades",
        params={
            "activa": "eq.true",
            "select": "id,argenprop_id,titulo,url,precio,moneda,anunciante_nombre,updated_at",
            "limit": str(limit),
            "order": "updated_at.asc.nullsfirst",
        },
    ) or []


def get_all_active_properties() -> list[dict[str, Any]]:
    """Obtiene el 100% de las propiedades marcadas como activas en Supabase paginando de a 1.000."""
    all_rows: list[dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        rows = _request(
            "GET",
            "argenprop_propiedades",
            params={
                "activa": "eq.true",
                "select": "id,argenprop_id,titulo,url,precio,moneda,anunciante_nombre,updated_at",
                "limit": str(limit),
                "offset": str(offset),
                "order": "id.asc",
            },
        )
        if not rows or not isinstance(rows, list):
            break
        all_rows.extend(rows)
        if len(rows) < limit:
            break
        offset += limit
    return all_rows


def check_argenprop_status(aid: str, retries: int = 2) -> tuple[int, str, bool]:
    """
    Comprueba en Argenprop si la propiedad sigue publicada o fue despublicada.
    URL canónica: https://www.argenprop.com/propiedad--{aid}
    Devuelve: (status_code, titulo_o_error, is_delisted)
    """
    target_url = f"https://www.argenprop.com/propiedad--{aid}"
    headers = {
        "Referer": "https://www.argenprop.com/",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-419,es;q=0.9",
    }

    for attempt in range(retries + 1):
        try:
            r = requests.get(target_url, impersonate="chrome110", headers=headers, timeout=12)
            code = r.status_code
            text = r.text or ""

            # WAF challenge: retry con breve backoff
            if code == 202 and attempt < retries:
                time.sleep(1.0 + attempt * 0.5)
                continue

            m_title = re.search(r"<title>(.*?)</title>", text, re.I)
            title = m_title.group(1).strip() if m_title else ""

            # Detección de CloudFront Rate Limit
            if code == 403 and ("request could not be satisfied" in text.lower() or "cloudfront" in text.lower()):
                return 403, "CLOUDFRONT_RATE_LIMIT", False

            # 410 Gone o 404 indican baja confirmada en Argenprop
            is_delisted = (
                code in (404, 410)
                or "410" in title
                or "404" in title
                or "no se encuentra disponible" in text.lower()
                or "aviso no disponible" in text.lower()
            )
            return code, title, is_delisted
        except Exception as exc:
            if attempt < retries:
                time.sleep(0.5)
                continue
            return 0, f"Error: {exc}", False

    return 0, "Max retries exceeded", False


def run_audit(
    all_activas: bool = False,
    sample_activas: int = 20,
    only_inactivas: bool = False,
    skip_inactivas: bool = False,
    auto_fix: bool = False,
    workers: int = 4,
    delay: float = 0.25,
    no_cache: bool = False,
    output_file: str | None = None,
):
    print("\n" + "=" * 75)
    print("🔍 AUDITORÍA DE BAJAS: ARGENPROP SALTA vs SUPABASE")
    print("=" * 75)

    _require_credentials()

    # ---------------------------------------------------------
    # PARTE 1: Auditoría de Inactivas (activa = false)
    # ---------------------------------------------------------
    falsos_positivos = []
    if not skip_inactivas:
        inactivas = get_inactive_properties()
        print(f"\n📂 [1/2] Auditando {len(inactivas)} propiedades marcadas como INACTIVAS en Supabase...")
        print("    Comprobando si en Argenprop efectivamente figuran dadas de baja (HTTP 410/404)...")

        results_inactivas = []

        for idx, p in enumerate(inactivas, 1):
            aid = str(p.get("argenprop_id"))
            code, title, is_delisted = check_argenprop_status(aid)

            verdict = "BAJA_CONFIRMADA" if is_delisted else ("ACTIVA_EN_WEB" if code == 200 else f"HTTP_{code}")
            item_res = {
                "id": p.get("id"),
                "argenprop_id": aid,
                "titulo": (p.get("titulo") or "")[:35],
                "code": code,
                "title_web": title[:30],
                "verdict": verdict,
                "motivo_db": p.get("motivo_baja"),
                "fecha_baja": str(p.get("fecha_baja") or "")[:10],
            }
            results_inactivas.append(item_res)

            if verdict == "BAJA_CONFIRMADA":
                print(f"  [{idx:02d}/{len(inactivas):02d}] ✅ ID {aid:8s} | HTTP {code:3d} (BAJA REAL) | Motivo: {p.get('motivo_baja')}")
            elif verdict == "ACTIVA_EN_WEB":
                falsos_positivos.append(item_res)
                print(f"  [{idx:02d}/{len(inactivas):02d}] ⚠️ ID {aid:8s} | HTTP 200 (¡SIGUE ACTIVA EN LA WEB!) | Título: {item_res['titulo']}")
            else:
                print(f"  [{idx:02d}/{len(inactivas):02d}] ℹ️ ID {aid:8s} | HTTP {code:3d} ({title})")

            time.sleep(0.15)

        bajas_ok = sum(1 for r in results_inactivas if r["verdict"] == "BAJA_CONFIRMADA")
        pct_bajas = (bajas_ok / max(1, len(results_inactivas))) * 100

        print("\n" + "-" * 75)
        print("📊 RESULTADO AUDITORÍA DE INACTIVAS:")
        print(f"  • Total en Supabase con activa=false:         {len(inactivas)}")
        print(f"  • Bajas legítimas confirmadas (HTTP 410/404): {bajas_ok} ({pct_bajas:.1f}%)")
        print(f"  • Falsos positivos (marcadas baja pero vivas): {len(falsos_positivos)}")
        print("-" * 75)

        if only_inactivas:
            print("\n🏁 Control de inactivas completado.")
            return
    else:
        print("\n⏩ Se omite la auditoría de inactivas (--skip-inactivas activado).")


    # ---------------------------------------------------------
    # PARTE 2: Auditoría de Activas (activa = true)
    # ---------------------------------------------------------
    if all_activas:
        print("\n📥 Obteniendo el total completo de propiedades ACTIVAS desde Supabase...")
        activas_to_check = get_all_active_properties()
        mode_desc = f"el 100% de las propiedades ({len(activas_to_check):,} totales)"
    else:
        activas_to_check = get_active_properties_sample(limit=sample_activas)
        mode_desc = f"muestra de {len(activas_to_check)} propiedades"

    total_activas = len(activas_to_check)
    vivas_count = 0
    nuevas_bajas_detectadas = []
    errores_count = 0

    # Cache de propiedades verificadas vivas
    verified_file = _ROOT / "data" / "verified_active_ids.txt"
    verified_file.parent.mkdir(parents=True, exist_ok=True)
    verified_ids: set[str] = set()
    if verified_file.exists():
        verified_ids = set(
            line.strip()
            for line in verified_file.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )

    if not no_cache and verified_ids and all_activas:
        already_ok = [p for p in activas_to_check if str(p.get("argenprop_id")) in verified_ids]
        activas_to_check = [p for p in activas_to_check if str(p.get("argenprop_id")) not in verified_ids]
        vivas_count += len(already_ok)
        if already_ok:
            print(f"  ℹ️ Se omiten {len(already_ok):,} propiedades ya verificadas vivas en la sesión previa.")
            print(f"  🎯 Restan auditar: {len(activas_to_check):,} propiedades activas.")

    pending_activas = len(activas_to_check)
    print(f"\n📂 [2/2] Auditando {pending_activas} ACTIVAS pendientes en Supabase ({workers} hilos, {delay}s delay)...")
    print("    Comprobando en Argenprop si siguen publicadas (200) o fueron dadas de baja (410/404)...\n")

    t_start = time.time()
    rate_limit_lock = threading.Lock()
    cache_lock = threading.Lock()
    paused_until = 0.0

    def _worker_task(prop_item: dict[str, Any]) -> tuple[dict[str, Any], int, str, bool]:
        nonlocal paused_until
        aid = str(prop_item.get("argenprop_id"))

        while True:
            now = time.time()
            if now < paused_until:
                time.sleep(paused_until - now + 0.5)

            if delay > 0:
                time.sleep(delay)

            c, t, delisted = check_argenprop_status(aid)
            if c == 403 and "CLOUDFRONT" in t:
                with rate_limit_lock:
                    if time.time() >= paused_until:
                        paused_until = time.time() + 180.0
                        print(f"\n⚠️  [CloudFront Rate Limit en ID {aid}] Pausando todos los hilos 3 min para enfriar WAF...")
                time.sleep(180.0)
                continue
            return prop_item, c, t, delisted

    processed = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(_worker_task, p): p for p in activas_to_check}
        for future in as_completed(futures):
            processed += 1
            try:
                p_item, code, title, is_delisted = future.result()
                aid = str(p_item.get("argenprop_id"))
                if is_delisted:
                    nuevas_bajas_detectadas.append({
                        "id": p_item.get("id"),
                        "argenprop_id": aid,
                        "titulo": (p_item.get("titulo") or "")[:40],
                        "precio": p_item.get("precio"),
                        "moneda": p_item.get("moneda"),
                        "inmobiliaria": p_item.get("anunciante_nombre"),
                        "code": code,
                        "url": f"https://www.argenprop.com/propiedad--{aid}",
                    })
                    print(f"  🚨 [{processed:4d}/{pending_activas}] ID {aid:8s} | HTTP {code:3d} -> ¡DADA DE BAJA! ({p_item.get('titulo', '')[:30]})")
                elif code == 200:
                    vivas_count += 1
                    with cache_lock:
                        with open(verified_file, "a", encoding="utf-8") as f:
                            f.write(f"{aid}\n")
                        verified_ids.add(aid)
                else:
                    errores_count += 1

            except Exception as exc:
                errores_count += 1

            # Reporte de avance cada 50 propiedades o al terminar
            if processed % 50 == 0 or processed == pending_activas:
                elapsed = max(0.1, time.time() - t_start)
                speed = processed / elapsed
                remaining = max(0, pending_activas - processed)
                eta_s = int(remaining / max(0.1, speed))
                eta_m = eta_s // 60
                eta_sec = eta_s % 60
                pct = (processed / max(1, pending_activas)) * 100
                print(
                    f"  ⏳ Progreso: {processed:4d}/{pending_activas} ({pct:5.1f}%) | "
                    f"Total Vivas: {vivas_count:4d} | Nuevas Bajas: {len(nuevas_bajas_detectadas):3d} | "
                    f"Velocidad: {speed:4.1f} req/s | ETA: {eta_m}m {eta_sec:02d}s"
                )

    total_elapsed = time.time() - t_start
    print("\n" + "-" * 75)
    print("📊 RESULTADO AUDITORÍA DE ACTIVAS:")
    print(f"  • Total en base de datos:               {total_activas:,}")
    print(f"  • Confirmadas vivas en la web (200):    {vivas_count:,}")
    print(f"  • Bajas pendientes detectadas (410/404):{len(nuevas_bajas_detectadas):,}")
    if errores_count:
        print(f"  • Avisos no concluyentes / timeout:     {errores_count}")
    print("-" * 75)


    # ---------------------------------------------------------
    # PARTE 3: Corrección Automática (si se especificó --fix)
    # ---------------------------------------------------------
    if auto_fix:
        print("\n🛠️ [CORRECCIÓN AUTOMÁTICA EN SUPABASE]")
        if nuevas_bajas_detectadas:
            ids_to_delist = [b["argenprop_id"] for b in nuevas_bajas_detectadas]
            marked = mark_delisted_batch(ids_to_delist, reason="removida_http_410")
            print(f"  ✅ {marked:,} propiedades actualizadas a activa=false (motivo: removida_http_410).")

        if falsos_positivos:
            now_str = datetime.now(UTC).isoformat()
            reactivadas = 0
            for fp in falsos_positivos:
                try:
                    update_property(
                        fp["id"],
                        {"activa": True, "fecha_baja": None, "motivo_baja": None, "updated_at": now_str},
                    )
                    reactivadas += 1
                except Exception as exc:
                    print(f"  ⚠️ Error reactivando ID {fp['argenprop_id']}: {exc}")
            print(f"  ✅ {reactivadas} falsos positivos reactivados a activa=true.")

        if not nuevas_bajas_detectadas and not falsos_positivos:
            print("  ℹ️ No se detectaron discrepancias. La base de datos está 100% sincronizada.")
    else:
        if nuevas_bajas_detectadas:
            print(
                f"\n💡 Nota: Se detectaron {len(nuevas_bajas_detectadas)} bajas pendientes en Argenprop.\n"
                f"   Para aplicarlas en Supabase, ejecuta el comando agregando la opción --fix"
            )

    # Guardar reporte JSON
    report_path = Path(output_file or (_ROOT / "data" / "audit_bajas_report.json"))
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "total_activas_analizadas": total_activas,
        "vivas_confirmadas": vivas_count,
        "bajas_detectadas_count": len(nuevas_bajas_detectadas),
        "falsos_positivos_count": len(falsos_positivos),
        "auto_fix_aplicado": auto_fix,
        "bajas_detectadas": nuevas_bajas_detectadas,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
    print(f"\n📄 Reporte detallado guardado en: {report_path.relative_to(_ROOT)}")

    print("\n" + "=" * 75)
    print("🏁 AUDITORÍA COMPLETADA EXITOSAMENTE")
    print("=" * 75 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Auditoría de bajas Argenprop vs Supabase")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Audita todas las propiedades activas de la base de datos (100%%)",
    )
    parser.add_argument(
        "--sample-activas",
        type=int,
        default=20,
        help="Cantidad de propiedades activas a auditar como muestra (default: 20 si no se usa --all)",
    )
    parser.add_argument(
        "--only-inactivas",
        action="store_true",
        help="Solo auditar las propiedades marcadas como inactivas",
    )
    parser.add_argument(
        "--skip-inactivas",
        action="store_true",
        help="Omite auditar las propiedades inactivas",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Aplica correcciones automáticas en Supabase si detecta discrepancias",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Número de hilos concurrentes (default: 4)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.25,
        help="Pausa en segundos entre peticiones por hilo (default: 0.25)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignora la caché de propiedades ya verificadas vivas",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Ruta donde guardar el reporte JSON detallado",
    )
    args = parser.parse_args()

    run_audit(
        all_activas=args.all,
        sample_activas=args.sample_activas,
        only_inactivas=args.only_inactivas,
        skip_inactivas=args.skip_inactivas,
        auto_fix=args.fix,
        workers=args.workers,
        delay=args.delay,
        no_cache=args.no_cache,
        output_file=args.output,
    )



if __name__ == "__main__":
    main()

