from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Iterator


@dataclass(frozen=True)
class RegionConfig:
    key: str
    loc: str
    provincia: str
    localidad: str
    table: str
    progress_type: str
    lock_type: str
    bands_cache_stem: str
    extra_locs: tuple[str, ...] = field(default_factory=tuple)


REGIONS: dict[str, RegionConfig] = {
    "salta": RegionConfig(
        key="salta",
        loc="salta",
        provincia="Salta",
        localidad="Salta",
        table="argenprop_properties",
        progress_type="argenprop_scrap_progress",
        lock_type="argenprop_scrap_lock",
        bands_cache_stem="price_bands_argenprop_salta",
        extra_locs=(
            "salta-arg",
            "cafayate",
            "tartagal",
            "oran",
            "metan",
            "general-guemes",
            "rosario-de-lerma",
            "chicoana",
            "cachi",
            "embarcacion",
            "san-lorenzo-salta",
            "vaqueros",
        ),
    ),
    "jujuy": RegionConfig(
        key="jujuy",
        loc="jujuy",
        provincia="Jujuy",
        localidad="Jujuy",
        table="argenprop_properties_jujuy",
        progress_type="argenprop_scrap_progress_jujuy",
        lock_type="argenprop_scrap_lock_jujuy",
        bands_cache_stem="price_bands_argenprop_jujuy",
    ),
}

_current: ContextVar[RegionConfig] = ContextVar(
    "argenprop_region",
    default=REGIONS["salta"],
)


def get_region() -> RegionConfig:
    return _current.get()


def resolve_region(key: str | None) -> RegionConfig:
    k = (key or "salta").strip().lower()
    if k not in REGIONS:
        raise ValueError(f"Región Argenprop desconocida: {key!r}. Válidas: {sorted(REGIONS)}")
    return REGIONS[k]


@contextmanager
def use_region(key: str | RegionConfig) -> Iterator[RegionConfig]:
    cfg = key if isinstance(key, RegionConfig) else resolve_region(key)
    token = _current.set(cfg)
    try:
        yield cfg
    finally:
        _current.reset(token)
