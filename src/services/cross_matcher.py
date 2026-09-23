"""
Cross-Portal Property Matcher: Argenprop vs Zonaprop
Detecta:
1. Propiedades Exclusivas en Argenprop (no publicadas en Zonaprop)
2. Propiedades Compartidas / Duplicadas en ambos portales
3. Comparativa de precios y días en mercado entre portales
"""

from __future__ import annotations

from collections import Counter
import json
import math
import re
import urllib.request
from typing import Any
from src.config import settings


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calcula la distancia geodésica en metros entre dos coordenadas GPS."""
    R = 6371000  # Radio medio de la Tierra en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


def normalize_phone(raw: str | None) -> str | None:
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", str(raw))
    # Extraer los últimos 7 dígitos para comparar teléfonos locales o internacionales
    return digits[-7:] if len(digits) >= 7 else None


def normalize_type(t: str | None) -> str:
    if not t:
        return "otro"
    low = t.lower()
    if any(x in low for x in ["depto", "departamento", "monoambiente"]):
        return "depto"
    if any(x in low for x in ["casa", "duplex", "dúplex", "chalet"]):
        return "casa"
    if any(x in low for x in ["terreno", "lote", "campo"]):
        return "terreno"
    if any(x in low for x in ["local", "oficina", "comercial"]):
        return "comercial"
    return "otro"


def normalize_op(op: str | None) -> str:
    if not op:
        return "venta"
    low = op.lower()
    if "alquiler" in low:
        return "alquiler"
    return "venta"


def fetch_supabase_table(table: str, select: str, filter_params: str = "activa=eq.true&limit=1000") -> list[dict]:
    url = f"{settings.supabase_url.rstrip('/')}/rest/v1/{table}?select={select}&{filter_params}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            return data if isinstance(data, list) else []
    except Exception as exc:
        print(f"Error fetching {table}: {exc}")
        return []


def is_generic_centroid(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    # Salta Capital centro default centroid pin (-24.78213, -65.42319)
    return abs(lat - (-24.78213)) < 0.0015 and abs(lon - (-65.42319)) < 0.0015


def extract_mza_lote(text: str) -> tuple[str | None, str | None]:
    m_mza = re.search(r'\b(?:mza|manzana)\s*[:#.]?\s*(\d+[a-z]?|[a-z])\b', text, re.I)
    m_lote = re.search(r'\b(?:lote|lt)\s*[:#.]?\s*(\d+[a-z]?|[a-z])\b', text, re.I)
    mza = m_mza.group(1).lower() if m_mza else None
    lote = m_lote.group(1).lower() if m_lote else None
    if mza in ["0", "00", "sn", "s/n"]:
        mza = None
    if lote in ["0", "00", "sn", "s/n"]:
        lote = None
    return mza, lote


def match_single_property(ap_prop: dict, zp_candidates: list[dict]) -> tuple[dict | None, int, list[str]]:
    """
    Compara una propiedad de Argenprop contra una lista de candidatos de Zonaprop.
    Retorna: (mejor_match_zonaprop, score, razones)
    """
    best_candidate = None
    best_score = 0
    best_reasons = []

    ap_op = normalize_op(ap_prop.get("tipo_operacion"))
    ap_type = normalize_type(ap_prop.get("tipo_propiedad"))
    ap_phone = normalize_phone(ap_prop.get("anunciante_telefono") or ap_prop.get("anunciante_whatsapp"))
    ap_anunc = (ap_prop.get("anunciante_nombre") or "").lower().replace("/", "").strip()
    ap_lat = ap_prop.get("latitud")
    ap_lon = ap_prop.get("longitud")
    ap_tot = ap_prop.get("superficie_total")
    ap_cub = ap_prop.get("superficie_cubierta")
    ap_price = ap_prop.get("precio")
    ap_cur = ap_prop.get("moneda")
    ap_dorm = ap_prop.get("dormitorios")

    # Precomputar regexes de la propiedad Argenprop una sola vez
    ap_full_txt = f"{ap_prop.get('ubicacion') or ''} {ap_prop.get('titulo') or ''} {ap_prop.get('descripcion') or ''}".lower()
    ap_mza, ap_lote = extract_mza_lote(ap_full_txt)
    ap_txt = f"{ap_prop.get('ubicacion') or ''} {ap_prop.get('titulo') or ''}".lower()
    m_ap = re.search(r'\b([a-záéíóúñ]{4,}(?:\s+[a-záéíóúñ]{4,})?)\s+(\d{2,5})\b', ap_txt)
    calle_ap = m_ap.group(1).strip() if m_ap else None
    num_ap = m_ap.group(2) if m_ap else None

    for zp in zp_candidates:
        score = 0
        reasons = []

        # 1. Operación (debe coincidir)
        zp_op = normalize_op(zp.get("tipo_operacion"))
        if ap_op != zp_op:
            continue

        # 2. Tipo (debe coincidir en categoría base)
        zp_type = normalize_type(zp.get("tipo_propiedad"))
        if ap_type != zp_type and ap_type != "otro" and zp_type != "otro":
            continue

        # 2b. Inmobiliaria coincidente (si ambas son la misma marca/agencia)
        zp_anunc = zp.get("_anunc") or (zp.get("anunciante_nombre") or "").lower().replace("/", "").strip()
        misma_inm = False
        if ap_anunc and zp_anunc and len(ap_anunc) >= 4 and len(zp_anunc) >= 4:
            if ap_anunc in zp_anunc or zp_anunc in ap_anunc:
                misma_inm = True
                score += 25
                reasons.append(f"Misma inmobiliaria ({ap_prop.get('anunciante_nombre')})")

        # 3. Teléfono coincidente
        zp_phone = zp.get("_phone") if "_phone" in zp else normalize_phone(zp.get("anunciante_telefono") or zp.get("anunciante_whatsapp"))
        if ap_phone and zp_phone and ap_phone == zp_phone:
            score += 35
            reasons.append(f"Mismo teléfono ({ap_phone})")

        # 4. Proximidad GPS
        zp_lat = zp.get("latitud")
        zp_lon = zp.get("longitud")
        dist = None
        if ap_lat is not None and ap_lon is not None and zp_lat is not None and zp_lon is not None:
            if is_generic_centroid(ap_lat, ap_lon) or is_generic_centroid(zp_lat, zp_lon):
                # Pin genérico de centro de Salta colocado por el portal
                score += 5
            else:
                dist = haversine_distance_meters(ap_lat, ap_lon, zp_lat, zp_lon)
                if dist <= 30:
                    score += 40
                    reasons.append(f"GPS idéntico ({dist:.0f}m)")
                elif dist <= 80:
                    score += 25
                    reasons.append(f"GPS muy cercano ({dist:.0f}m)")
                elif dist <= 200:
                    score += 10
                    reasons.append(f"GPS cercano ({dist:.0f}m)")
                elif dist > 600:
                    score -= 40

        # 5. Verificación de Manzana y Lote
        zp_mza = zp.get("_mza")
        zp_lote = zp.get("_lote")
        if "_mza" not in zp:
            zp_full_txt = f"{zp.get('ubicacion') or ''} {zp.get('titulo') or ''} {zp.get('descripcion') or ''}".lower()
            zp_mza, zp_lote = extract_mza_lote(zp_full_txt)
            zp["_mza"], zp["_lote"] = zp_mza, zp_lote

        if ap_mza and zp_mza and ap_mza != zp_mza:
            score -= 50
        elif ap_mza and zp_mza and ap_mza == zp_mza:
            score += 25
            reasons.append(f"Misma Mza ({ap_mza.upper()})")

        if ap_lote and zp_lote and ap_lote != zp_lote:
            score -= 50
        elif ap_lote and zp_lote and ap_lote == zp_lote:
            score += 25
            reasons.append(f"Mismo Lote ({ap_lote})")

        # 6. Superficie inteligente (compara total o cubierta)
        zp_tot = zp.get("superficie_total")
        zp_cub = zp.get("superficie_cubierta")

        diff_tot = abs(ap_tot - zp_tot) / max(ap_tot, zp_tot) if (ap_tot and zp_tot and ap_tot > 0 and zp_tot > 0) else None
        diff_cub = abs(ap_cub - zp_cub) / max(ap_cub, zp_cub) if (ap_cub and zp_cub and ap_cub > 0 and zp_cub > 0) else None

        best_diff = None
        best_sup_label = None
        if diff_tot is not None and diff_cub is not None:
            if diff_tot <= diff_cub:
                best_diff = diff_tot
                best_sup_label = f"~{ap_tot:.0f}m²"
            else:
                best_diff = diff_cub
                best_sup_label = f"~{ap_cub:.0f}m² cub."
        elif diff_tot is not None:
            best_diff = diff_tot
            best_sup_label = f"~{ap_tot:.0f}m²"
        elif diff_cub is not None:
            best_diff = diff_cub
            best_sup_label = f"~{ap_cub:.0f}m² cub."

        if best_diff is not None:
            if best_diff <= 0.03:
                score += 20
                reasons.append(f"Superficie idéntica ({best_sup_label})")
            elif best_diff <= 0.08:
                score += 15
                reasons.append(f"Superficie similar ({best_sup_label})")
            elif best_diff <= 0.15:
                if ap_type == "terreno" and not (ap_phone and zp_phone and ap_phone == zp_phone) and not misma_inm:
                    score -= 30
                else:
                    score += 5
                    reasons.append(f"Superficie aproximada ({best_sup_label})")
            elif best_diff > 0.25 and not (ap_phone and zp_phone and ap_phone == zp_phone) and not misma_inm:
                score -= 35

        # 7. Precio
        zp_price = zp.get("precio")
        zp_cur = zp.get("moneda")
        if ap_price and zp_price and ap_cur and zp_cur and ap_cur == zp_cur:
            p_diff = abs(ap_price - zp_price) / max(ap_price, zp_price)
            if p_diff == 0:
                score += 15
                reasons.append(f"Mismo precio ({ap_cur} {ap_price:,.0f})")
            elif p_diff <= 0.05:
                score += 10
                reasons.append(f"Precio cercano (dif {p_diff*100:.1f}%)")
            elif p_diff > 0.12 and not (ap_phone and zp_phone and ap_phone == zp_phone):
                score -= 40
            elif p_diff > 0.20 and not (ap_phone and zp_phone and ap_phone == zp_phone):
                score -= 60

        # 8. Dirección (Calle y Altura coincidente)
        if calle_ap and num_ap:
            zp_txt = zp.get("_txt") or f"{zp.get('ubicacion') or ''} {zp.get('titulo') or ''}".lower()
            if calle_ap in zp_txt and num_ap in zp_txt:
                score += 35
                reasons.append(f"Misma calle y altura ({calle_ap.title()} {num_ap})")

        # 9. Dormitorios coincidentes
        zp_dorm = zp.get("dormitorios")
        if ap_dorm and zp_dorm and ap_dorm > 0 and ap_dorm == zp_dorm:
            score += 10
            reasons.append(f"{ap_dorm} dorm.")

        if score > best_score:
            best_score = score
            best_candidate = zp
            best_reasons = reasons

    return best_candidate, best_score, best_reasons


def analyze_cross_market(limit_ap: int | None = None) -> dict[str, Any]:
    """
    Ejecuta el cruce inteligente entre las propiedades de Argenprop y Zonaprop en Supabase.
    Si limit_ap es None, cruza el 100% del catálogo.
    """
    ap_cols = "id,argenprop_id,titulo,tipo_propiedad,tipo_operacion,precio,moneda,ubicacion,barrio,latitud,longitud,superficie_total,superficie_cubierta,dormitorios,anunciante_nombre,anunciante_telefono,anunciante_whatsapp,url,imagen_principal,publicado_hace"
    zp_cols = "id,zonaprop_id,titulo,tipo_propiedad,tipo_operacion,precio,moneda,ubicacion,barrio,latitud,longitud,superficie_total,superficie_cubierta,dormitorios,anunciante_nombre,anunciante_telefono,anunciante_whatsapp,url,imagen_principal,publicado_hace"

    print("📥 Descargando propiedades de Argenprop desde Supabase...")
    filter_ap = f"activa=eq.true&limit={limit_ap}" if limit_ap else "activa=eq.true&limit=10000"
    ap_props = fetch_supabase_table("argenprop_propiedades", select=ap_cols, filter_params=filter_ap)
    print(f"  -> {len(ap_props)} propiedades obtenidas de Argenprop.")

    print("📥 Descargando propiedades de Zonaprop desde Supabase...")
    zp_props = fetch_supabase_table("zonaprop_propiedades", select=zp_cols, filter_params="activa=eq.true&limit=10000")
    print(f"  -> {len(zp_props)} propiedades obtenidas de Zonaprop.")

    # Pre-indexar Zonaprop por tipo de operación y precalcular campos para ultra-velocidad
    zp_by_op: dict[str, list[dict]] = {}
    for zp in zp_props:
        op = normalize_op(zp.get("tipo_operacion"))
        zp["_op"] = op
        zp["_type"] = normalize_type(zp.get("tipo_propiedad"))
        zp["_anunc"] = (zp.get("anunciante_nombre") or "").lower().replace("/", "").strip()
        zp["_phone"] = normalize_phone(zp.get("anunciante_telefono") or zp.get("anunciante_whatsapp"))
        zp_txt = f"{zp.get('ubicacion') or ''} {zp.get('titulo') or ''}".lower()
        zp["_txt"] = zp_txt
        zp_full_txt = f"{zp_txt} {zp.get('descripcion') or ''}".lower()
        mza, lote = extract_mza_lote(zp_full_txt)
        zp["_mza"] = mza
        zp["_lote"] = lote
        zp_by_op.setdefault(op, []).append(zp)

    exclusivas_argenprop = []
    compartidas = []

    for ap in ap_props:
        ap_op = normalize_op(ap.get("tipo_operacion"))
        candidates = zp_by_op.get(ap_op, zp_props)
        best_zp, score, reasons = match_single_property(ap, candidates)
        has_anchor = any(
            ("GPS" in r and "genérico" not in r)
            or ("teléfono" in r.lower())
            or ("calle" in r.lower())
            or ("misma inmobiliaria" in r.lower())
            for r in reasons
        )
        if best_zp and score >= 60 and has_anchor:
            compartidas.append({
                "argenprop": ap,
                "zonaprop": best_zp,
                "score": score,
                "reasons": reasons,
                "precio_diff_usd": (ap.get("precio") or 0) - (best_zp.get("precio") or 0) if ap.get("moneda") == best_zp.get("moneda") else None,
            })
        else:
            exclusivas_argenprop.append({
                "argenprop": ap,
                "best_candidate": best_zp,
                "best_score": score,
            })

    c_zp = Counter((z.get("anunciante_nombre") or "Dueño Directo / Particular").strip() for z in zp_props)

    return {
        "total_argenprop": len(ap_props),
        "total_zonaprop_analizadas": len(zp_props),
        "exclusivas_argenprop_count": len(exclusivas_argenprop),
        "compartidas_count": len(compartidas),
        "porcentaje_exclusividad_argenprop": round((len(exclusivas_argenprop) / max(1, len(ap_props))) * 100, 1),
        "exclusivas_argenprop": exclusivas_argenprop,
        "compartidas": compartidas,
        "all_ap_props": ap_props,
        "zonaprop_anunciantes": dict(c_zp.most_common(50)),
    }


def persist_cross_matches_to_supabase(batch_size: int = 100) -> dict[str, Any]:
    """
    Ejecuta el matching completo Argenprop vs Zonaprop y persiste en Supabase:
    - es_compartida: True / False
    - es_exclusiva: True / False
    - grupo_compartida_id: "zp_<zonaprop_id>" si hay match, None si es exclusiva
    - anunciantes_grupo: lista de nombres de inmobiliarias anunciantes
    - cantidad_inmobiliarias: cantidad de agencias distintas
    """
    from datetime import UTC, datetime
    from src.db.mapper import to_supabase_record
    from src.db.supabase_client import upsert_batch_properties

    print("\n🔗 [CROSS-MATCHER] Iniciando cruce inteligente Argenprop vs Zonaprop...")
    analysis = analyze_cross_market(limit_ap=None)

    ap_props = analysis.get("all_ap_props") or []
    compartidas = {str(c["argenprop"]["argenprop_id"]): c for c in analysis.get("compartidas", [])}

    print(f"  📊 Resultados del cruce: {len(compartidas)} compartidas, {analysis['exclusivas_argenprop_count']} exclusivas.")
    print("  💾 Persistiendo flags de exclusividad y grupos compartidos en Supabase...")

    records_to_update = []
    now = datetime.now(UTC)

    for ap in ap_props:
        aid = str(ap.get("argenprop_id"))
        ap_anunc = (ap.get("anunciante_nombre") or "").strip()

        if aid in compartidas:
            match = compartidas[aid]
            zp = match["zonaprop"]
            zp_anunc = (zp.get("anunciante_nombre") or "").strip()
            anunciantes = [a for a in dict.fromkeys([ap_anunc, zp_anunc]) if a]

            ap["es_compartida"] = True
            ap["es_exclusiva"] = False
            ap["grupo_compartida_id"] = f"zp_{zp.get('zonaprop_id')}"
            ap["anunciantes_grupo"] = anunciantes
            ap["cantidad_inmobiliarias"] = max(1, len(anunciantes))
        else:
            anunciantes = [ap_anunc] if ap_anunc else []
            ap["es_compartida"] = False
            ap["es_exclusiva"] = True
            ap["grupo_compartida_id"] = None
            ap["anunciantes_grupo"] = anunciantes
            ap["cantidad_inmobiliarias"] = 1

        rec = to_supabase_record(ap, now=now, is_insert=True)
        records_to_update.append(rec)

    # Bulk update a Supabase
    updated_count = 0
    errors_count = 0
    for i in range(0, len(records_to_update), batch_size):
        chunk = records_to_update[i:i + batch_size]
        try:
            upsert_batch_properties(chunk)
            updated_count += len(chunk)
        except Exception as exc:
            print(f"⚠️ Error actualizando chunk de cruce ({exc}), guardando individualmente...")
            from src.db import supabase_client as sb
            for r in chunk:
                try:
                    aid = r.get("argenprop_id")
                    existing = sb.get_by_argenprop_id(aid)
                    if existing:
                        sb.update_property(existing["id"], r)
                        updated_count += 1
                except Exception:
                    errors_count += 1

    print(f"  ✅ Persistencia completada: {updated_count} propiedades actualizadas, {errors_count} errores.")
    return {
        "ok": errors_count == 0,
        "total": len(ap_props),
        "compartidas": len(compartidas),
        "exclusivas": analysis["exclusivas_argenprop_count"],
        "porcentaje_exclusividad": analysis["porcentaje_exclusividad_argenprop"],
        "updated": updated_count,
        "errors": errors_count,
    }

