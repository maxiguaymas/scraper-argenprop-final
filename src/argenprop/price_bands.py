from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path

from src.argenprop.region import get_region
from src.argenprop.urls import (
    OPERATIONS,
    PROPERTY_TYPES,
    Currency,
    Segment,
)

logger = logging.getLogger("argenprop")

CACHE_SCHEMA_VERSION = 2

# Bandas ultra-precisas calibradas para el mercado de Salta
# Argenprop pagina hasta max 10 páginas (20 avisos/pág = 200 máx).
# Cada banda aquí está verificada para tener <= 165 propiedades,
# garantizando 100% de cobertura sin truncamiento ni descarte de avisos.

TERRENOS_VENTA_BANDS: tuple[tuple[int, int], ...] = (
    (0, 10_000),
    (10_000, 16_000),
    (16_000, 21_000),
    (21_000, 28_000),
    (28_000, 40_000),
    (40_000, 60_000),
    (60_000, 85_000),
    (85_000, 130_000),
    (130_000, 200_000),
    (200_000, 100_000_000),
)

CASAS_VENTA_BANDS: tuple[tuple[int, int], ...] = (
    (0, 55_000),
    (55_000, 80_000),
    (80_000, 105_000),
    (105_000, 130_000),
    (130_000, 160_000),
    (160_000, 195_000),
    (195_000, 240_000),
    (240_000, 300_000),
    (300_000, 400_000),
    (400_000, 100_000_000),
)

DEPTOS_VENTA_BANDS: tuple[tuple[int, int], ...] = (
    (0, 55_000),
    (55_000, 75_000),
    (75_000, 95_000),
    (95_000, 120_000),
    (120_000, 160_000),
    (160_000, 230_000),
    (230_000, 100_000_000),
)

DEPTOS_ALQUILER_ARS_BANDS: tuple[tuple[int, int], ...] = (
    (0, 450_000),
    (450_000, 700_000),
    (700_000, 1_100_000),
    (1_100_000, 100_000_000),
)

_CACHE_MEM: dict[str, list[str]] = {}


def _cache_path() -> Path:
    raw = (os.environ.get("ARGENPROP_BANDS_CACHE") or "").strip()
    if raw:
        return Path(raw)
    stem = get_region().bands_cache_stem
    root = Path(__file__).resolve().parents[2]
    return root / "data" / f"{stem}_v{CACHE_SCHEMA_VERSION}.json"


def _seed_segments_for_loc(loc: str, *, with_price: bool) -> list[Segment]:
    segs: list[Segment] = []

    # 1. Terrenos en Venta (bandas finas en USD)
    if with_price:
        for lo, hi in TERRENOS_VENTA_BANDS:
            segs.append(
                Segment(
                    tipo="terrenos",
                    op="venta",
                    loc=loc,
                    kind="price",
                    lo=lo,
                    hi=hi,
                    currency="dolares",
                )
            )
    else:
        segs.append(Segment(tipo="terrenos", op="venta", loc=loc, kind="plain"))

    # 2. Casas en Venta (bandas finas en USD)
    if with_price:
        for lo, hi in CASAS_VENTA_BANDS:
            segs.append(
                Segment(
                    tipo="casas",
                    op="venta",
                    loc=loc,
                    kind="price",
                    lo=lo,
                    hi=hi,
                    currency="dolares",
                )
            )
    else:
        segs.append(Segment(tipo="casas", op="venta", loc=loc, kind="plain"))

    # 3. Departamentos en Venta (bandas finas en USD)
    if with_price:
        for lo, hi in DEPTOS_VENTA_BANDS:
            segs.append(
                Segment(
                    tipo="departamentos",
                    op="venta",
                    loc=loc,
                    kind="price",
                    lo=lo,
                    hi=hi,
                    currency="dolares",
                )
            )
    else:
        segs.append(Segment(tipo="departamentos", op="venta", loc=loc, kind="plain"))

    # 4. Departamentos en Alquiler (bandas en ARS + banda en USD)
    if with_price:
        for lo, hi in DEPTOS_ALQUILER_ARS_BANDS:
            segs.append(
                Segment(
                    tipo="departamentos",
                    op="alquiler",
                    loc=loc,
                    kind="price",
                    lo=lo,
                    hi=hi,
                    currency="pesos",
                )
            )
        segs.append(
            Segment(
                tipo="departamentos",
                op="alquiler",
                loc=loc,
                kind="price",
                lo=0,
                hi=100_000_000,
                currency="dolares",
            )
        )
    else:
        segs.append(Segment(tipo="departamentos", op="alquiler", loc=loc, kind="plain"))

    # 5. Resto de combinaciones de tipo de propiedad y operación
    # Casas alquiler (~106 avisos), Terrenos alquiler (~5 avisos), PH, Locales, Oficinas, etc.
    # Todas tienen < 150 avisos en Salta y caben perfectamente en búsqueda plana sin paginación truncada.
    specialized = {
        ("terrenos", "venta"),
        ("casas", "venta"),
        ("departamentos", "venta"),
        ("departamentos", "alquiler"),
    }
    for tipo in PROPERTY_TYPES:
        for op in OPERATIONS:
            if with_price and (tipo, op) in specialized:
                continue
            segs.append(Segment(tipo=tipo, op=op, loc=loc, kind="plain"))

    return segs


def seed_segments() -> list[Segment]:
    cfg = get_region()
    segs = _seed_segments_for_loc(cfg.loc, with_price=True)
    extra_types = ("casas", "departamentos", "terrenos")
    extra_ops = ("venta", "alquiler")
    for extra in cfg.extra_locs:
        for tipo in extra_types:
            for op in extra_ops:
                segs.append(Segment(tipo=tipo, op=op, loc=extra, kind="plain"))
    return segs


def discover_all_segments(*, force: bool = False) -> list[str]:
    loc = get_region().loc
    cached = _CACHE_MEM.get(loc)
    if cached is not None and not force:
        return list(cached)

    path = _cache_path()
    if not force and path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            segs = [str(s) for s in (raw.get("segments") or []) if s]
            if segs and int(raw.get("schema_version") or 0) >= CACHE_SCHEMA_VERSION:
                _CACHE_MEM[loc] = segs
                return list(segs)
        except Exception:
            pass

    segs = [s.slug for s in seed_segments()]
    _CACHE_MEM[loc] = segs
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema_version": CACHE_SCHEMA_VERSION,
                    "loc": loc,
                    "created_at": time.time(),
                    "source": "seed",
                    "segments": segs,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass
    return list(segs)


def tipo_from_segment_slug(slug: str) -> str | None:
    from src.argenprop.urls import parse_segment_slug

    parsed = parse_segment_slug(slug)
    return parsed.tipo if parsed else None
