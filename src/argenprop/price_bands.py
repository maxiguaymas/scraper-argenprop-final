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

CACHE_SCHEMA_VERSION = 1

SEED_USD_BANDS: tuple[tuple[int, int], ...] = (
    (0, 80_000),
    (80_000, 130_000),
    (130_000, 200_000),
    (200_000, 350_000),
    (350_000, 100_000_000),
)

SEED_ARS_BANDS: tuple[tuple[int, int], ...] = (
    (0, 400_000),
    (400_000, 800_000),
    (800_000, 1_500_000),
    (1_500_000, 100_000_000),
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
    for tipo in PROPERTY_TYPES:
        for op in OPERATIONS:
            currency: Currency = "dolares" if op == "venta" else "pesos"
            if with_price and tipo in ("casas", "departamentos", "terrenos"):
                bands = SEED_USD_BANDS if currency == "dolares" else SEED_ARS_BANDS
                for lo, hi in bands:
                    segs.append(
                        Segment(
                            tipo=tipo,
                            op=op,
                            loc=loc,
                            kind="price",
                            lo=lo,
                            hi=hi,
                            currency=currency,
                        )
                    )
            else:
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
