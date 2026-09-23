from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def to_property_dict(prop: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    ts = now or datetime.now(UTC)
    price = prop.get("precio")
    sup_tot = prop.get("superficie_total")
    price_m2 = None
    if price and sup_tot and sup_tot > 0 and price > 0:
        price_m2 = round(price / sup_tot, 2)

    return {
        "argenprop_id": str(prop["argenprop_id"]),
        "titulo": prop.get("titulo"),
        "titulo_generado": prop.get("titulo_generado"),
        "tipo_propiedad": prop.get("tipo_propiedad"),
        "tipo_operacion": prop.get("tipo_operacion"),
        "precio": price,
        "moneda": prop.get("moneda"),
        "expensas": prop.get("expensas"),
        "expensas_moneda": prop.get("expensas_moneda", "ARS"),
        "superficie_total": sup_tot,
        "superficie_cubierta": prop.get("superficie_cubierta"),
        "precio_m2": price_m2,
        "ambientes": prop.get("ambientes") or 0,
        "dormitorios": prop.get("dormitorios") or 0,
        "banos": prop.get("banos") or 0,
        "cocheras": prop.get("cocheras") or 0,
        "direccion": prop.get("direccion"),
        "barrio": prop.get("barrio"),
        "ubicacion": prop.get("ubicacion"),
        "localidad": prop.get("localidad") or "Salta",
        "provincia": prop.get("provincia") or "Salta",
        "latitud": prop.get("latitud"),
        "longitud": prop.get("longitud"),
        "coordenadas_origen": prop.get("coordenadas_origen"),
        "url": prop.get("url"),
        "imagen_principal": prop.get("imagen_principal"),
        "imagenes": prop.get("imagenes") or [],
        "descripcion": prop.get("descripcion"),
        "anunciante_nombre": prop.get("anunciante_nombre"),
        "anunciante_logo": prop.get("anunciante_logo"),
        "anunciante_cucis": prop.get("anunciante_cucis"),
        "anunciante_telefono": prop.get("anunciante_telefono"),
        "anunciante_whatsapp": prop.get("anunciante_whatsapp"),
        "visualizaciones": prop.get("visualizaciones"),
        "publicado_hace": prop.get("publicado_hace"),
        "fecha_publicacion": prop.get("fecha_publicacion"),
        "es_super_destacado": bool(
            prop.get("es_super_destacado") or prop.get("nivel_destacado") == "super_destacado"
        ),
        "nivel_destacado": prop.get("nivel_destacado") or "ninguno",
        "apto_credito": bool(prop.get("apto_credito")),
        "a_estrenar": bool(prop.get("a_estrenar")),
        "pagina_origen": prop.get("pagina_origen"),
        "estado": prop.get("estado") or "activo",
        "features": prop.get("features") or {},
        "raw_data": prop.get("raw_data") or {},
        "activa": True,
        "ultima_actualizacion": ts,
    }


SUPABASE_COLUMNS = {
    "argenprop_id",
    "titulo",
    "tipo_propiedad",
    "tipo_operacion",
    "precio",
    "moneda",
    "expensas",
    "ubicacion",
    "barrio",
    "localidad",
    "provincia",
    "latitud",
    "longitud",
    "coordenadas_origen",
    "superficie_total",
    "superficie_cubierta",
    "ambientes",
    "dormitorios",
    "banos",
    "cocheras",
    "descripcion",
    "anunciante_nombre",
    "anunciante_logo",
    "anunciante_cucis",
    "anunciante_telefono",
    "anunciante_whatsapp",
    "es_super_destacado",
    "nivel_destacado",
    "url",
    "imagen_principal",
    "imagenes",
    "tags",
    "visualizaciones",
    "publicado_hace",
    "fecha_publicacion",
    "anunciante_nivel",
    "anunciante_calificaciones",
    "raw_data",
    "pagina_origen",
    "primera_vez_visto",
    "ultima_actualizacion",
    "activa",
    "created_at",
    "updated_at",
    "apto_credito",
    "a_estrenar",
    "estado",
    "es_exclusiva",
    "es_compartida",
    "cantidad_inmobiliarias",
    "grupo_compartida_id",
    "anunciantes_grupo",
    "fecha_baja",
    "motivo_baja",
    "informacion_ia",
    "informacion_ia_updated_at",
}


def to_supabase_record(
    prop: dict[str, Any],
    *,
    now: datetime | None = None,
    is_insert: bool = True,
) -> dict[str, Any]:
    """Genera un registro sanitizado y validado exactamente para la tabla argenprop_propiedades en Supabase."""
    ts_dt = now or datetime.now(UTC)
    ts = ts_dt.isoformat()

    price = prop.get("precio")
    sup_tot = prop.get("superficie_total")
    price_m2 = prop.get("precio_m2")
    if price_m2 is None and price and sup_tot and sup_tot > 0 and price > 0:
        price_m2 = round(price / sup_tot, 2)

    # Nivel de destaque
    pts = prop.get("visualizaciones")
    es_super = bool(
        prop.get("es_super_destacado")
        or prop.get("nivel_destacado") == "super_destacado"
        or (pts and pts >= 2000)
    )
    nivel_dest = prop.get("nivel_destacado")
    if not nivel_dest or nivel_dest == "ninguno":
        if es_super:
            nivel_dest = "super_destacado"
        elif pts and pts >= 1000:
            nivel_dest = "destacado"
        else:
            nivel_dest = "comun"

    # Fechas
    fecha_pub = prop.get("fecha_publicacion")
    if isinstance(fecha_pub, datetime):
        fecha_pub = fecha_pub.strftime("%Y-%m-%d")
    elif isinstance(fecha_pub, str) and len(fecha_pub) >= 10:
        fecha_pub = fecha_pub[:10]
    else:
        fecha_pub = None

    # Ubicación limpia
    ubicacion = prop.get("ubicacion")
    if not ubicacion:
        parts = [prop.get("direccion"), prop.get("barrio"), prop.get("localidad") or "Salta"]
        ubicacion = ", ".join([p for p in parts if p])

    # Raw data & Tags
    raw = prop.get("raw_data")
    raw_data = raw if isinstance(raw, dict) else {}
    tags = prop.get("tags")
    if not isinstance(tags, list):
        tags = []

    # Coordenadas
    lat = prop.get("latitud")
    lon = prop.get("longitud")
    coord_orig = prop.get("coordenadas_origen")
    try:
        lat = float(lat) if lat is not None else None
        lon = float(lon) if lon is not None else None
    except (ValueError, TypeError):
        lat, lon = None, None

    record = {
        "titulo": prop.get("titulo"),
        "tipo_propiedad": prop.get("tipo_propiedad"),
        "tipo_operacion": prop.get("tipo_operacion"),
        "precio": float(price) if price is not None else None,
        "moneda": prop.get("moneda"),
        "expensas": float(prop.get("expensas")) if prop.get("expensas") is not None else None,
        "ubicacion": ubicacion,
        "barrio": prop.get("barrio"),
        "localidad": prop.get("localidad") or "Salta",
        "provincia": prop.get("provincia") or "Salta",
        "latitud": lat,
        "longitud": lon,
        "coordenadas_origen": coord_orig if (lat and lon) else None,
        "superficie_total": float(sup_tot) if sup_tot is not None else None,
        "superficie_cubierta": float(prop.get("superficie_cubierta")) if prop.get("superficie_cubierta") is not None else None,
        "ambientes": int(prop.get("ambientes") or 0),
        "dormitorios": int(prop.get("dormitorios") or 0),
        "banos": int(prop.get("banos") or 0),
        "cocheras": int(prop.get("cocheras") or 0),
        "descripcion": prop.get("descripcion"),
        "anunciante_nombre": prop.get("anunciante_nombre"),
        "anunciante_logo": prop.get("anunciante_logo"),
        "anunciante_cucis": prop.get("anunciante_cucis"),
        "anunciante_telefono": prop.get("anunciante_telefono"),
        "anunciante_whatsapp": prop.get("anunciante_whatsapp"),
        "es_super_destacado": es_super,
        "nivel_destacado": nivel_dest,
        "url": prop.get("url"),
        "imagen_principal": prop.get("imagen_principal"),
        "imagenes": prop.get("imagenes") if isinstance(prop.get("imagenes"), list) else [],
        "tags": tags,
        "visualizaciones": int(pts) if pts is not None else None,
        "publicado_hace": prop.get("publicado_hace"),
        "fecha_publicacion": fecha_pub,
        "precio_m2": float(price_m2) if price_m2 is not None else None,
        "raw_data": raw_data,
        "pagina_origen": prop.get("pagina_origen"),
        "ultima_actualizacion": ts,
        "updated_at": ts,
        "activa": True,
        "apto_credito": bool(prop.get("apto_credito")),
        "a_estrenar": bool(prop.get("a_estrenar")),
        "estado": prop.get("estado") or "activo",
    }

    # Campos de Cruce Inteligente (Cross-Portal Matcher)
    if "es_exclusiva" in prop:
        record["es_exclusiva"] = bool(prop.get("es_exclusiva"))
    if "es_compartida" in prop:
        record["es_compartida"] = bool(prop.get("es_compartida"))
    if "grupo_compartida_id" in prop:
        record["grupo_compartida_id"] = prop.get("grupo_compartida_id")
    if "anunciantes_grupo" in prop:
        record["anunciantes_grupo"] = prop.get("anunciantes_grupo") or []
    if "cantidad_inmobiliarias" in prop:
        record["cantidad_inmobiliarias"] = int(prop.get("cantidad_inmobiliarias") or 1)

    # Campos de Bajas y Despublicadas
    if "fecha_baja" in prop:
        record["fecha_baja"] = prop.get("fecha_baja")
    if "motivo_baja" in prop:
        record["motivo_baja"] = prop.get("motivo_baja")
    if "activa" in prop:
        record["activa"] = bool(prop.get("activa"))

    if prop.get("argenprop_id"):
        record["argenprop_id"] = str(prop["argenprop_id"])

    if is_insert:
        record["primera_vez_visto"] = ts
        record["created_at"] = ts

    # Filtrar estrictamente solo las columnas que existen en Supabase
    filtered = {k: v for k, v in record.items() if k in SUPABASE_COLUMNS}

    if not is_insert:
        # En updates (PATCH), solo mandar campos con valor presente en prop para no sobreescribir columnas NOT NULL con None
        filtered = {
            k: v
            for k, v in filtered.items()
            if v is not None and (k in prop or k in ("ultima_actualizacion", "updated_at"))
        }

    return filtered
