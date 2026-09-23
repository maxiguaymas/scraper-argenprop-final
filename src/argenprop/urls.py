from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

BASE = "https://www.argenprop.com"

Currency = Literal["dolares", "pesos"]

PROPERTY_TYPES = (
    "casas",
    "departamentos",
    "ph",
    "terrenos",
    "locales",
    "campos",
    "quintas",
    "oficinas",
    "cocheras",
    "galpones",
    "fondos-de-comercio",
    "hoteles",
)

OPERATIONS = ("venta", "alquiler", "alquiler-temporal")

RESIDENTIAL_TYPES = frozenset({"casas", "departamentos", "ph", "quintas"})

MAX_SAFE_PAGE = 10
MAX_SAFE_LISTINGS = 180

_LISTING_ID_IN_URL_RE = re.compile(r"--(\d{4,})(?:[/?#]|$)", re.I)


def is_valid_listing_url(url: str | None, aid: str | None = None) -> bool:
    """True solo para fichas reales (`/casa-en-venta-en-...--123`), no `/-123` ni inmobiliarias."""
    if not url:
        return False
    u = str(url).strip()
    if "argenprop.com" not in u.lower():
        return False
    if "/inmobiliarias/" in u.lower():
        return False
    m = _LISTING_ID_IN_URL_RE.search(u)
    if not m:
        return False
    found = m.group(1)
    if aid and str(aid) != found:
        return False
    if re.search(rf"argenprop\.com/-{found}(?:[/?#]|$)", u, re.I):
        return False
    return True


def absolute_listing_url(path: str) -> str:
    raw = (path or "").strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw.split("?")[0].split("#")[0]
    if not raw.startswith("/"):
        raw = "/" + raw
    return f"{BASE}{raw.split('?')[0].split('#')[0]}"


@dataclass(frozen=True)
class Segment:
    tipo: str
    op: str
    loc: str
    kind: Literal["price", "dorms", "plain"] = "plain"
    lo: int | None = None
    hi: int | None = None
    currency: Currency | None = None
    dorms: int | None = None

    @property
    def slug(self) -> str:
        if self.kind == "price" and self.lo is not None and self.hi is not None and self.currency:
            return f"{self.tipo}-{self.op}-{self.loc}-{self.lo}-{self.hi}-{self.currency}"
        if self.kind == "dorms" and self.dorms is not None:
            dorm_slug = "1-dormitorio" if self.dorms == 1 else f"{self.dorms}-dormitorios"
            return f"{self.tipo}-{self.op}-{self.loc}-{dorm_slug}"
        return f"{self.tipo}-{self.op}-{self.loc}"

    def path(self) -> str:
        base = f"/{self.tipo}/{self.op}/{self.loc}"
        if self.kind == "price" and self.lo is not None and self.hi is not None and self.currency:
            return f"{base}/{int(self.lo)}-{int(self.hi)}-{self.currency}"
        if self.kind == "dorms" and self.dorms is not None:
            dorm_slug = "1-dormitorio" if self.dorms == 1 else f"{self.dorms}-dormitorios"
            return f"{base}/{dorm_slug}"
        return base


def listing_url(segment: Segment, page: int = 1) -> str:
    p = max(1, min(int(page), MAX_SAFE_PAGE))
    url = f"{BASE}{segment.path()}"
    if p > 1:
        return f"{url}?pagina-{p}"
    return url


def direct_listing_url(base_url: str, page: int = 1) -> str:
    """Construye URL para un link directo como /inmuebles/alquiler-o-venta/salta-arg."""
    clean = base_url.split("?")[0].split("#")[0].rstrip("/")
    if page <= 1:
        return clean
    return f"{clean}?pagina-{page}"


def parse_segment_slug(slug: str) -> Segment | None:
    s = (slug or "").strip().lower().strip("/")
    if not s:
        return None
    tipo = None
    for t in sorted(PROPERTY_TYPES, key=len, reverse=True):
        if s.startswith(t + "-"):
            tipo = t
            rest = s[len(t) + 1 :]
            break
    if not tipo:
        return None
    op = None
    for candidate in ("alquiler-temporal", "alquiler", "venta"):
        if rest.startswith(candidate + "-") or rest == candidate:
            op = candidate
            rest = rest[len(candidate) :].lstrip("-")
            break
    if not op:
        return None

    loc = rest
    kind: Literal["price", "dorms", "plain"] = "plain"
    lo = hi = dorms = None
    currency: Currency | None = None

    price_m = re.search(r"^(.+)-(\d+)-(\d+)-(dolares|pesos)$", rest)
    dorm_m = re.search(r"^(.+)-(\d+)-dormitorios?$", rest)
    if price_m:
        loc = price_m.group(1)
        lo = int(price_m.group(2))
        hi = int(price_m.group(3))
        currency = price_m.group(4)  # type: ignore[assignment]
        kind = "price"
    elif dorm_m:
        loc = dorm_m.group(1)
        dorms = int(dorm_m.group(2))
        kind = "dorms"

    if not loc:
        return None
    return Segment(
        tipo=tipo,
        op=op,
        loc=loc,
        kind=kind,
        lo=lo,
        hi=hi,
        currency=currency,
        dorms=dorms,
    )
