from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import re
from html import unescape
from typing import Any

from src.argenprop.urls import is_valid_listing_url

_LAT_BOUNDS = (-56.0, -21.0)
_LON_BOUNDS = (-74.0, -53.0)

_SETVIEW_RE = re.compile(
    r'''setView\(\s*\[\s*(-?\d+[.,]\d{2,})\s*,\s*(-?\d+[.,]\d{2,})''',
    re.I,
)
_LD_GEO_RE = re.compile(
    r'''"@type"\s*:\s*"GeoCoordinates"[\s\S]{0,240}?"latitude"\s*:\s*"?(-?\d+[.,]\d{2,})"?'''
    r'''[\s\S]{0,120}?"longitude"\s*:\s*"?(-?\d+[.,]\d{2,})"?''',
    re.I,
)
_DATA_LAT_RE = re.compile(
    r'''data-lat(?:itude)?\s*=\s*["'](-?\d+[.,]\d{2,})["']''',
    re.I,
)
_DATA_LON_RE = re.compile(
    r'''data-(?:longitude|lng|lon)\s*=\s*["'](-?\d+[.,]\d{2,})["']''',
    re.I,
)
_JSON_LAT_RE = re.compile(
    r'''["'](?:lat|latitude|latitud)["']\s*:\s*["']?(-?\d+[.,]\d{2,})["']?''',
    re.I,
)
_JSON_LON_RE = re.compile(
    r'''["'](?:lng|lon|long|longitude|longitud)["']\s*:\s*["']?(-?\d+[.,]\d{2,})["']?''',
    re.I,
)
_TEL_HREF_RE = re.compile(r"""href=["']tel:([^"']+)["']""", re.I)
_WHATSAPP_RE = re.compile(
    r"(?:wa\.me/|whatsapp\.com/send\?phone=)(\+?\d{7,15})",
    re.I,
)
_DESC_CONTENT_RE = re.compile(
    r'class="[^"]*section-description--content[^"]*"[^>]*>(.*?)</(?:div|p|section)>',
    re.I | re.S,
)


def _parse_coord(raw: str | None) -> float | None:
    if not raw:
        return None
    text = unescape(str(raw)).strip().replace(" ", "").replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _valid_ar_pair(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return _LAT_BOUNDS[0] <= lat <= _LAT_BOUNDS[1] and _LON_BOUNDS[0] <= lon <= _LON_BOUNDS[1]


def extract_map_coords(html: str) -> tuple[float | None, float | None]:
    if not html:
        return None, None

    # 1. Leaflet map script (más preciso)
    m = _SETVIEW_RE.search(html)
    if m:
        lat = _parse_coord(m.group(1))
        lon = _parse_coord(m.group(2))
        if _valid_ar_pair(lat, lon):
            return lat, lon

    # 2. JSON-LD GeoCoordinates
    m_ld = _LD_GEO_RE.search(html)
    if m_ld:
        lat = _parse_coord(m_ld.group(1))
        lon = _parse_coord(m_ld.group(2))
        if _valid_ar_pair(lat, lon):
            return lat, lon

    # 3. data-lat / data-lon
    m_lat = _DATA_LAT_RE.search(html)
    m_lon = _DATA_LON_RE.search(html)
    if m_lat and m_lon:
        lat = _parse_coord(m_lat.group(1))
        lon = _parse_coord(m_lon.group(1))
        if _valid_ar_pair(lat, lon):
            return lat, lon

    # 4. JSON embedded props
    m_jlat = _JSON_LAT_RE.search(html)
    m_jlon = _JSON_LON_RE.search(html)
    if m_jlat and m_jlon:
        lat = _parse_coord(m_jlat.group(1))
        lon = _parse_coord(m_jlon.group(1))
        if _valid_ar_pair(lat, lon):
            return lat, lon

    return None, None


_PHONE_DIV_RE = re.compile(
    r'class=["\'][^"\']*(?:form-detail-phone-number|details-phone-number|agent-phone|card__agent--phone)[^"\']*["\'][^>]*>([\s\S]*?)</',
    re.I,
)


def extract_phone(html: str) -> str | None:
    if not html:
        return None
    m_tel = _TEL_HREF_RE.search(html)
    if m_tel:
        phone = re.sub(r"[^\d+]", "", m_tel.group(1))
        if len(phone) >= 7:
            return phone
    m_wa = _WHATSAPP_RE.search(html)
    if m_wa:
        return m_wa.group(1)
    m_div = _PHONE_DIV_RE.search(html)
    if m_div:
        clean = re.sub(r"[^\d+]", "", m_div.group(1))
        if len(clean) >= 6:
            return clean
    m_attr = re.search(r'data-(?:phone|telefono)=["\']([^"\']+)["\']', html, re.I)
    if m_attr:
        clean = re.sub(r"[^\d+]", "", m_attr.group(1))
        if len(clean) >= 6:
            return clean
    return None


def extract_full_description(html: str) -> str | None:
    if not html:
        return None
    m = _DESC_CONTENT_RE.search(html)
    if m:
        clean = re.sub(r"<[^>]+>", " ", m.group(1))
        clean = re.sub(r"\s+", " ", unescape(clean)).strip()
        if len(clean) >= 20:
            return clean[:4000]
    return None


def extract_ficha_images(html: str) -> list[str]:
    if not html:
        return []
    imgs: list[str] = []

    # 1. Extraer imágenes del visor de galería (data-open-gallery)
    for st in re.findall(r'data-open-gallery=[^>]*style=["\']([^"\']+)["\']', html, re.I):
        m_u = re.search(r'url\([\'"]?(https://[^\'")]+)[\'"]?\)', st)
        if m_u:
            u = m_u.group(1).strip()
            high_res = re.sub(r'_(?:u_)?(?:small|medium|thumb)\.jpg', '.jpg', u)
            if high_res not in imgs and "placeholder" not in high_res:
                imgs.append(high_res)

    # 2. Detectar carpeta del aviso desde og:image
    folder_id = None
    m_og = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\'](https://[^"\']+)["\']', html, re.I)
    if not m_og:
        m_og = re.search(r'<meta[^>]+content=["\'](https://[^"\']+)["\'][^>]+property=["\']og:image["\']', html, re.I)
    if m_og:
        og_url = m_og.group(1)
        m_fold = re.search(r'/static-content/(\d+)/', og_url)
        if m_fold:
            folder_id = m_fold.group(1)
        og_high = re.sub(r'_(?:u_)?(?:small|medium|thumb)\.jpg', '.jpg', og_url)
        if og_high not in imgs and "placeholder" not in og_high:
            imgs.insert(0, og_high)

    # 3. Si se identificó la carpeta de este aviso, buscar todas las fotos de esa carpeta en el HTML
    if folder_id:
        pattern = rf'https://(?:www\.)?argenprop\.com/static-content/{folder_id}/[a-f0-9\-]+[^\s"\'<>()]*\.jpg'
        for u in re.findall(pattern, html, re.I):
            high_res = re.sub(r'_(?:u_)?(?:small|medium|thumb)\.jpg', '.jpg', u)
            if high_res not in imgs and "placeholder" not in high_res:
                imgs.append(high_res)

    # 4. Fallback si no hubo carpeta: buscar fotos de static-content excluyendo logos de agencia (_a/)
    if not imgs:
        matches = re.findall(
            r'(https://(?:www\.)?argenprop\.com/static-content/\d+/[a-f0-9\-]+[^\s"\'<>()]*\.jpg)',
            html,
            re.I,
        )
        for u in matches:
            if "placeholder" in u or "avatar" in u or "_a/" in u:
                continue
            high_res = re.sub(r'_(?:u_)?(?:small|medium|thumb)\.jpg', '.jpg', u)
            if high_res not in imgs:
                imgs.append(high_res)

    return imgs


def extract_detail_fields(html: str) -> dict[str, Any]:
    lat, lon = extract_map_coords(html)
    phone = extract_phone(html)
    desc = extract_full_description(html)
    imgs = extract_ficha_images(html)

    fields: dict[str, Any] = {}
    if lat is not None and lon is not None:
        fields["latitud"] = lat
        fields["longitud"] = lon
        fields["coordenadas_origen"] = "leaflet_map"
    if phone:
        fields["anunciante_telefono"] = phone
        wa = phone
        if not wa.startswith("+"):
            if len(wa) == 10:
                wa = f"+549{wa}"
            elif len(wa) == 7:
                wa = f"+549387{wa}"
        fields["anunciante_whatsapp"] = wa
    if desc:
        fields["descripcion"] = desc
    if imgs:
        fields["imagenes"] = imgs

    return fields


def extract_fields_from_api_json(data: dict[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}

    # Coordenadas
    lat = data.get("Direccion_Latitud_d")
    lon = data.get("Direccion_Longitud_d")
    if lat is not None and lon is not None:
        try:
            f_lat, f_lon = float(lat), float(lon)
            if _valid_ar_pair(f_lat, f_lon):
                fields["latitud"] = f_lat
                fields["longitud"] = f_lon
                fields["coordenadas_origen"] = "sosiva_api"
        except (ValueError, TypeError):
            pass

    if "coordenadas_origen" not in fields:
        fields["coordenadas_origen"] = "sin_coordenadas"

    # Dirección y Ubicación desglosada
    calle = (data.get("Direccion_NombreCalle_t") or "").strip()
    num = data.get("Direccion_Numero_i")
    piso = (data.get("Direccion_Piso_t") or "").strip()
    depto = (data.get("Direccion_Departamento_t") or "").strip()

    dir_parts = []
    if calle:
        dir_parts.append(f"{calle} {num}" if num and num > 0 else calle)
    if piso:
        dir_parts.append(f"Piso {piso}")
    if depto:
        dir_parts.append(f"Depto {depto}")

    full_dir = ", ".join(dir_parts) if dir_parts else None
    if full_dir:
        fields["direccion"] = full_dir

    barrio = (data.get("Barrio_t") or data.get("BarrioCalculado_t") or "").strip() or None
    if barrio:
        fields["barrio"] = barrio

    localidad = (data.get("Localidad_t") or "").strip() or "Salta"
    provincia = (data.get("Provincia_t") or "").strip() or "Salta"
    fields["localidad"] = localidad
    fields["provincia"] = provincia

    ubic_elements = [full_dir, barrio, localidad]
    fields["ubicacion"] = ", ".join([x for x in ubic_elements if x])

    # Fechas y Días en el mercado
    f_pub = data.get("FechaPublicacionAviso_dt")
    if f_pub:
        try:
            iso_clean = str(f_pub).replace("Z", "+00:00")
            dt_pub = datetime.fromisoformat(iso_clean)
            now = datetime.now(timezone.utc)
            dias_mercado = max(0, (now - dt_pub).days)
            fields["fecha_publicacion"] = dt_pub.strftime("%Y-%m-%d")
            if dias_mercado == 0:
                fields["publicado_hace"] = "Publicado hoy"
            elif dias_mercado == 1:
                fields["publicado_hace"] = "Hace 1 día"
            else:
                fields["publicado_hace"] = f"Hace {dias_mercado} días"
        except Exception:
            fields["fecha_publicacion"] = str(f_pub)[:10]

    # Teléfono y WhatsApp
    phone = data.get("TelefonoContacto_t")
    if phone:
        clean = re.sub(r"[^\d+]", "", str(phone))
        if len(clean) >= 6:
            fields["anunciante_telefono"] = clean
            wa = clean
            if not wa.startswith("+"):
                if len(wa) == 10:
                    wa = f"+549{wa}"
                elif len(wa) == 7:
                    wa = f"+549387{wa}"
            fields["anunciante_whatsapp"] = wa

    # Descripción
    desc = data.get("InformacionAdicional_t") or data.get("DescripcionSeo_t")
    if desc:
        fields["descripcion"] = str(desc).strip()[:4000]

    # Imágenes completas (HD original)
    media = data.get("Multimedia_s")
    if media and isinstance(media, list):
        imgs = []
        for m in media:
            if isinstance(m, dict):
                u = m.get("Url") or m.get("Large") or m.get("Medium")
                if u and u not in imgs and "placeholder" not in str(u):
                    imgs.append(u)
        if imgs:
            fields["imagenes"] = imgs

    # Puntos / visualizaciones
    puntos = data.get("Puntos_i")
    if puntos is not None:
        try:
            fields["visualizaciones"] = int(puntos)
        except (ValueError, TypeError):
            pass

    # Destaque según ID y puntos oficiales de Argenprop
    id_dest = data.get("IdTipoDestaque_i")
    pts = fields.get("visualizaciones")
    if id_dest in (1, 2) or (pts and pts >= 2000):
        fields["es_super_destacado"] = True
        fields["nivel_destacado"] = "super_destacado"
    elif id_dest in (3, 4) or (pts and pts >= 1000):
        fields["es_super_destacado"] = False
        fields["nivel_destacado"] = "destacado"
    else:
        fields["es_super_destacado"] = False
        fields["nivel_destacado"] = "comun"

    return fields


async def enrich_single_listing(
    session: Any,
    url: str,
    aid: str,
    referer: str | None = None,
) -> dict[str, Any]:
    if not is_valid_listing_url(url, aid):
        return {}

    # 1. API interna de Argenprop (sosiva451) -> ultra rápida, sin WAF y con datos 100% completos
    if hasattr(session, "get_json") and aid:
        try:
            api_url = f"https://api.sosiva451.com/Avisos/{aid}"
            data = await session.get_json(api_url)
            if data and isinstance(data, dict) and data.get("IdAviso"):
                return extract_fields_from_api_json(data)
        except Exception:
            pass

    # Si la API no lo encuentra, la propiedad ya fue dada de baja o no está disponible
    return {}
