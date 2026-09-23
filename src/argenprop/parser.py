from __future__ import annotations

import re
from html import unescape
from typing import Any

from src.argenprop.region import get_region
from src.argenprop.urls import absolute_listing_url, is_valid_listing_url

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_HREF_RE = re.compile(
    r"""(?:href|data-href|data-url)\s*=\s*(['"])(?:https?://(?:www\.)?argenprop\.com)?(/(?!inmobiliarias/)[^"'#?]+--(\d{4,}))\1""",
    re.I,
)
_UNQUOTED_HREF_RE = re.compile(
    r"""(?:href|data-href)\s*=\s*(/(?!inmobiliarias/)[^\s>]+--(\d{4,}))""",
    re.I,
)
_PATH_ANY_RE = re.compile(
    r"(/(?:casa|departamento|depto|ph|terreno|local|campo|quinta|oficina|"
    r"cochera|galp[oó]n|fondo|hotel|deposito|depósito|consultorio|edificio|"
    r"inmueble|negocio)[^\s\"'<>]*--(\d{4,}))",
    re.I,
)
_DATA_ID_RE = re.compile(
    r'data-(?:id|item-card|id-aviso)\s*=\s*["\'](\d{4,})["\']',
    re.I,
)
_DATA_ATTR_RE = re.compile(
    r'data-([a-z0-9\-]+)\s*=\s*["\']([^"\']*)["\']',
    re.I,
)
_PRICE_TEXT_RE = re.compile(
    r"(?:(USD|U\$S|US\$)|(\$))\s*([\d.]+)",
    re.I,
)
_EXPENSAS_RE = re.compile(r"\+\s*\$\s*([\d.]+)\s*expensas", re.I)
_M2_RE = re.compile(r"([\d.,]+)\s*m[²2](?:\s*(cubie\.?|cubierta|tot(?:al)?|terreno))?", re.I)
_DORM_RE = re.compile(r"(\d+)\s*dorm", re.I)
_BANO_RE = re.compile(r"(\d+)\s*ba[ñn]os?", re.I)
_AMB_RE = re.compile(r"(\d+)\s*amb", re.I)
_COCHERA_RE = re.compile(r"(\d+)\s*cochera", re.I)
_IMG_RE = re.compile(
    r'(?:src|data-src|data-lazy|data-original)="(https://[^"]+)"',
    re.I,
)
_CARD_SPLIT_RE = re.compile(
    r'<div[^>]*class="[^"]*(?:listing__item(?!s)|listing-card|card-item)[^"]*"[^>]*>',
    re.I,
)
_CARD_POINTS_RE = re.compile(
    r'class="[^"]*card__points[^"]*"[^>]*>(.*?)</',
    re.I | re.S,
)
_AGENT_ALT_RE = re.compile(
    r'class="[^"]*card__agent[^"]*"[\s\S]{0,900}?alt=["\']([^"\']+)["\']',
    re.I,
)
_AGENT_LOGO_RE = re.compile(
    r'class="[^"]*card__agent[^"]*"[\s\S]{0,900}?(?:data-src|data-lazy-src|src)="(https://[^"]+)"',
    re.I,
)
_SEGMENTO_MAP = {
    "superior": "super_destacado",
    "destacado": "destacado",
    "premium": "destacado",
    "intermedia": "destacado",
    "especial": "destacado",
    "exacto": "comun",
    "basico": "comun",
    "básico": "comun",
    "otros": "comun",
}
_MONEDA_ID = {"1": "ARS", "2": "USD"}


def classify_argenprop_destaque(
    tiposegmento: str | None = None,
    puntos: int | None = None,
    card_html: str = "",
) -> tuple[str, bool]:
    """
    Clasifica el aviso en:
    - 'super_destacado' (True): tiposegmento 'superior', o >= 2000 puntos
    - 'destacado' (False): tiposegmento 'destacado'/'premium'/'intermedia', o 1000..1999 puntos
    - 'comun' (False): estándar, < 1000 puntos
    """
    seg = (tiposegmento or "").strip().lower()
    low = card_html.lower()
    if seg in ("superior", "super_destacado", "super") or "super-destacado" in low or "card-featured--super" in low:
        return "super_destacado", True
    if seg in ("destacado", "premium", "intermedia", "especial") or "destacado" in low:
        return "destacado", False
    if puntos is not None:
        if puntos >= 2000:
            return "super_destacado", True
        if puntos >= 1000:
            return "destacado", False
    return "comun", False


def parse_ar_int(value: str | None) -> int | None:
    if value is None:
        return None
    raw = unescape(str(value)).strip().replace("\xa0", "").replace(" ", "")
    if not raw:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        return int(raw.replace(".", ""))
    if re.fullmatch(r"\d+", raw):
        return int(raw)
    digits = re.sub(r"[^\d]", "", raw.split(",")[0])
    return int(digits) if digits else None


def parse_ar_float(value: str | None) -> float | None:
    if value is None:
        return None
    raw = unescape(str(value)).strip().replace("\xa0", "").replace(" ", "")
    if not raw:
        return None
    if re.fullmatch(r"\d{1,3}(\.\d{3})+", raw):
        return float(raw.replace(".", ""))
    if re.fullmatch(r"\d+", raw):
        return float(raw)
    try:
        norm = raw.replace(".", "").replace(",", ".")
        return float(norm)
    except ValueError:
        return None


def _strip(html: str) -> str:
    t = _TAG_RE.sub(" ", html)
    return _WS_RE.sub(" ", unescape(t)).strip()


def _attr(card: str, *names: str) -> str | None:
    for k, v in _DATA_ATTR_RE.findall(card):
        if k.lower() in names and v.strip():
            return unescape(v.strip())
    return None


def _bare(card: str, attr_name: str) -> str | None:
    m = re.search(
        rf'\b{re.escape(attr_name)}\s*=\s*["\']([^"\']*)["\']',
        card,
        re.I,
    )
    return unescape(m.group(1).strip()) if m and m.group(1).strip() else None


def extract_total_from_html(html: str) -> int | None:
    """Extrae el total de avisos del listado."""
    if not html:
        return None
    m_track = re.search(r'totalavisos\s*=\s*["\'](\d+)["\']', html, re.I)
    if m_track:
        return int(m_track.group(1))

    m_h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", html, re.I)
    if m_h1:
        txt = _strip(m_h1.group(1))
        m_num = re.search(r"^([\d.]+)\s+(?:inmuebles|propiedades|casas|departamentos)", txt, re.I)
        if m_num:
            return parse_ar_int(m_num.group(1))

    m_title = re.search(r"<title>([\s\S]*?)</title>", html, re.I)
    if m_title:
        txt = _strip(m_title.group(1))
        m_num = re.search(r"^([\d.]+)\s+", txt)
        if m_num:
            return parse_ar_int(m_num.group(1))
    return None


def find_listing_path(chunk: str, aid: str | None = None) -> str | None:
    for m in _HREF_RE.finditer(chunk):
        path = m.group(2)
        url_aid = m.group(3)
        if aid and url_aid != aid:
            continue
        if is_valid_listing_url(absolute_listing_url(path), aid or url_aid):
            return path
    for m in _UNQUOTED_HREF_RE.finditer(chunk):
        path = m.group(1)
        url_aid = m.group(2)
        if aid and url_aid != aid:
            continue
        if is_valid_listing_url(absolute_listing_url(path), aid or url_aid):
            return path
    for m in _PATH_ANY_RE.finditer(chunk):
        path = m.group(1)
        url_aid = m.group(2)
        if aid and url_aid != aid:
            continue
        if is_valid_listing_url(absolute_listing_url(path), aid or url_aid):
            return path
    return None


def _split_into_cards(html: str) -> list[str]:
    splits = [m.start() for m in _CARD_SPLIT_RE.finditer(html)]
    if len(splits) >= 2:
        cards = []
        for i, start in enumerate(splits):
            end = splits[i + 1] if i + 1 < len(splits) else min(len(html), start + 8000)
            cards.append(html[start:end])
        return cards

    # Fallback si no divide bien por clase
    chunks = []
    seen = set()
    for m in _HREF_RE.finditer(html):
        aid = m.group(3)
        if aid in seen:
            continue
        seen.add(aid)
        start = max(0, m.start() - 1500)
        end = min(len(html), m.end() + 4000)
        chunks.append(html[start:end])
    return chunks


def parse_listing_card(
    card: str,
    *,
    pagina_origen: int | None = None,
    tipo_hint: str | None = None,
    op_hint: str | None = None,
) -> dict[str, Any] | None:
    aid = None
    href_m = _HREF_RE.search(card) or _UNQUOTED_HREF_RE.search(card)
    if href_m and href_m.lastindex and href_m.lastindex >= 2:
        aid = href_m.group(3) if href_m.re is _HREF_RE else href_m.group(2)
    if not aid:
        aid = _bare(card, "idaviso") or _bare(card, "data-item-card")
    if not aid:
        dm = _DATA_ID_RE.search(card)
        aid = dm.group(1) if dm else None
    if not aid:
        im = re.search(r'<div[^>]*\bid=["\'](\d{4,})["\']', card, re.I)
        aid = im.group(1) if im else None
    if not aid:
        return None

    rel = find_listing_path(card, aid)
    if not rel:
        return None
    url = absolute_listing_url(rel)
    if not is_valid_listing_url(url, aid):
        return None

    text = _strip(card)

    # Moneda
    moneda = _MONEDA_ID.get(_bare(card, "idmoneda") or "")
    if not moneda:
        moneda = (_attr(card, "price-currency", "pricecurrency", "currency") or "").upper() or None
    if moneda in ("DOLAR", "DOLARES", "U$S", "US$"):
        moneda = "USD"
    if moneda in ("PESO", "PESOS", "ARS", "$"):
        moneda = "ARS"

    # Precio: Priorizar montooperacion (valor real pactado en la moneda original)
    raw_precio = (
        _bare(card, "montooperacion")
        or _bare(card, "montonormalizado")
        or _attr(card, "price", "price-normalized")
    )
    precio = parse_ar_float(raw_precio)

    if precio is None:
        pm = _PRICE_TEXT_RE.search(text)
        if pm:
            precio = parse_ar_float(pm.group(3))
            moneda = moneda or ("USD" if pm.group(1) else "ARS")

    if precio is not None and precio <= 0:
        precio = None
        moneda = None
    if "consultar" in text.lower() and precio is None:
        moneda = None

    # Expensas
    expensas = None
    exp_m = _EXPENSAS_RE.search(text)
    if exp_m:
        expensas = parse_ar_float(exp_m.group(1))

    # Superficie
    sup_tot = None
    sup_cub = None
    for m in _M2_RE.finditer(text):
        val = parse_ar_float(m.group(1))
        qual = (m.group(2) or "").lower()
        if "cubie" in qual:
            sup_cub = val
        else:
            sup_tot = val
    if sup_tot is None and sup_cub is not None:
        sup_tot = sup_cub

    # Ambientes, Dormitorios, Baños, Cocheras
    dorms = parse_ar_int(_bare(card, "dormitorios") or _attr(card, "bedrooms"))
    if dorms is None:
        dm = _DORM_RE.search(text)
        dorms = int(dm.group(1)) if dm else None

    amb = parse_ar_int(_bare(card, "ambientes") or _attr(card, "rooms"))
    if amb is None:
        am = _AMB_RE.search(text)
        amb = int(am.group(1)) if am else None

    banos = parse_ar_int(_attr(card, "bathrooms"))
    if banos is None:
        bm = _BANO_RE.search(text)
        banos = int(bm.group(1)) if bm else None

    cocheras = parse_ar_int(_attr(card, "garages"))
    if cocheras is None:
        cm = _COCHERA_RE.search(text)
        cocheras = int(cm.group(1)) if cm else None

    # Visualizaciones (puntos)
    views = parse_ar_int(_bare(card, "puntos"))
    if views is None:
        pm_pts = _CARD_POINTS_RE.search(card)
        if pm_pts:
            views = parse_ar_int(_strip(pm_pts.group(1)))
    if views is None:
        vm = re.search(r"Visto\s+([\d.]+)", text, re.I)
        if vm:
            views = parse_ar_int(vm.group(1))

    # Nivel destacado
    seg = _bare(card, "tiposegmento")
    nivel_dest, es_super = classify_argenprop_destaque(seg, views, card)

    # Título y Dirección
    titulo = None
    tm = re.search(r'class="[^"]*card__title[^"]*"[^>]*>(.*?)</', card, re.I | re.S)
    if tm:
        titulo = _strip(tm.group(1))

    direccion = None
    dm = re.search(r'class="[^"]*card__address[^"]*"[^>]*>(.*?)</', card, re.I | re.S)
    if dm:
        direccion = _strip(dm.group(1))

    # Anunciante
    anunciante_nombre = None
    alt_m = _AGENT_ALT_RE.search(card)
    if alt_m:
        anunciante_nombre = unescape(alt_m.group(1).strip())

    anunciante_logo = None
    logo_m = _AGENT_LOGO_RE.search(card)
    if logo_m:
        anunciante_logo = logo_m.group(1)

    # Fotos
    fotos = []
    for im in _IMG_RE.finditer(card):
        img_url = im.group(1)
        if "placeholder" not in img_url and "avatar" not in img_url:
            fotos.append(img_url)
    fotos = list(dict.fromkeys(fotos))
    imagen_principal = fotos[0] if fotos else None

    # Tipo de propiedad y operación
    tipo_prop = tipo_hint
    tipo_op = op_hint
    low_url = rel.lower()
    if not tipo_prop:
        for tp in ("departamento", "casa", "terreno", "ph", "local", "oficina", "cochera", "campo"):
            if tp in low_url:
                tipo_prop = tp
                break
    if not tipo_op:
        if "alquiler-temporal" in low_url:
            tipo_op = "alquiler temporal"
        elif "alquiler" in low_url:
            tipo_op = "alquiler"
        elif "venta" in low_url:
            tipo_op = "venta"

    region = get_region()
    localidad = region.localidad
    provincia = region.provincia
    ubicacion = f"{direccion}, {localidad}" if direccion else localidad

    return {
        "argenprop_id": aid,
        "url": url,
        "titulo": titulo,
        "tipo_propiedad": tipo_prop or "inmueble",
        "tipo_operacion": tipo_op or "venta",
        "precio": precio,
        "moneda": moneda or "USD",
        "expensas": expensas,
        "superficie_total": sup_tot,
        "superficie_cubierta": sup_cub,
        "ambientes": amb,
        "dormitorios": dorms,
        "banos": banos,
        "cocheras": cocheras,
        "direccion": direccion,
        "barrio": None,
        "ubicacion": ubicacion,
        "localidad": localidad,
        "provincia": provincia,
        "descripcion": text[:1000] if text else None,
        "anunciante_nombre": anunciante_nombre,
        "anunciante_logo": anunciante_logo,
        "anunciante_telefono": None,
        "anunciante_whatsapp": None,
        "es_super_destacado": nivel_dest == "super_destacado",
        "nivel_destacado": nivel_dest,
        "apto_credito": "crédito" in text.lower(),
        "a_estrenar": "estrenar" in text.lower(),
        "pagina_origen": pagina_origen,
        "imagen_principal": imagen_principal,
        "imagenes": fotos,
        "visualizaciones": views,
        "estado": "activo",
        "raw_data": {"source": "argenprop_scraper", "card_text": text[:500]},
    }


def parse_listings_html(
    html: str,
    *,
    pagina_origen: int | None = None,
    tipo_hint: str | None = None,
    op_hint: str | None = None,
) -> list[dict[str, Any]]:
    cards = _split_into_cards(html)
    out = []
    seen = set()
    for card_html in cards:
        item = parse_listing_card(
            card_html,
            pagina_origen=pagina_origen,
            tipo_hint=tipo_hint,
            op_hint=op_hint,
        )
        if not item:
            continue
        aid = item["argenprop_id"]
        if aid in seen:
            continue
        seen.add(aid)
        out.append(item)
    return out
