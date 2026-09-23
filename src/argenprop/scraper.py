from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.argenprop.parser import extract_total_from_html, parse_listings_html
from src.argenprop.price_bands import discover_all_segments, tipo_from_segment_slug
from src.argenprop.session import ApSession
from src.argenprop.urls import (
    BASE,
    MAX_SAFE_PAGE,
    direct_listing_url,
    listing_url,
    parse_segment_slug,
)
from src.config import settings

logger = logging.getLogger("argenprop")


async def scrape_direct_url(
    target_url: str,
    *,
    session: ApSession,
    max_pages: int | None = None,
    limit: int = 500,
) -> dict[str, Any]:
    """Scrapea directamente una URL dada (ej. /inmuebles/alquiler-o-venta/salta-arg) página a página."""
    results: list[dict[str, Any]] = []
    seen: set[str] = set()
    total_found: int | None = None
    pages_visited = 0

    effective_max_pages = max_pages if max_pages is not None else max(10, (limit + 19) // 20)

    clean_url = target_url.strip()
    print(f"\n  🎯 Scrapeo directo URL: {clean_url}")

    for p in range(1, effective_max_pages + 1):
        page_url = direct_listing_url(clean_url, page=p)
        referer = direct_listing_url(clean_url, page=p - 1) if p > 1 else f"{BASE}/"
        print(f"  📄 Página {p}/{effective_max_pages}: {page_url}")

        html = await session.get_html(page_url, referer=referer)
        if session.waf_blocked:
            print("  ⛔ AWS WAF detectado — abortando.")
            break
        if not html:
            print(f"  ⚠️ No se pudo obtener contenido de pág {p}")
            break

        if total_found is None:
            total_found = extract_total_from_html(html)
            if total_found:
                print(f"  ℹ️ Total estimado informado por Argenprop: {total_found} propiedades")

        listings = parse_listings_html(html, pagina_origen=p)
        if not listings:
            print(f"  ⚠️ Sin avisos en página {p}. Fin de listado.")
            break

        added = 0
        for item in listings:
            aid = item.get("argenprop_id")
            if aid and aid not in seen:
                seen.add(aid)
                results.append(item)
                added += 1
                if len(results) >= limit:
                    break

        print(f"  Pág {p}: +{added} nuevas ({len(results)}/{limit} total acumulado)")
        pages_visited += 1

        if len(results) >= limit:
            break

        # Si la página trajo menos de 10 avisos en pág > 1, probablemente sea la última
        if len(listings) < 10 and p > 1:
            break

        await asyncio.sleep(0.4)

    return {
        "listings": results,
        "total_estimated": total_found,
        "pages_visited": pages_visited,
        "waf_blocked": session.waf_blocked,
    }


def _segment_cursor_from_page(page: int) -> tuple[str, int, int] | None:
    if page < 1:
        return None
    segments = discover_all_segments()
    idx = page - 1
    seg_i = idx // MAX_SAFE_PAGE
    seg_p = (idx % MAX_SAFE_PAGE) + 1
    if seg_i >= len(segments):
        return None
    return segments[seg_i], seg_p, seg_i


def _cursor_page_for_segment(seg_i: int, seg_p: int = 1) -> int:
    p = max(1, min(int(seg_p), MAX_SAFE_PAGE))
    return int(seg_i) * MAX_SAFE_PAGE + p


async def scrape_catalog_segmented(
    *,
    session: ApSession,
    start_page: int = 1,
    limit: int = 200,
    max_pages: int | None = None,
) -> dict[str, Any]:
    """Scrapea el catálogo mediante segmentación adaptativa para superar el tope de 10 páginas."""
    page = max(1, int(start_page))
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    empty_streak = 0
    pages_visited = 0
    effective_max_pages = max_pages if max_pages is not None else max(40, (limit + 19) // 20 + 20)

    while len(results) < limit and pages_visited < effective_max_pages and empty_streak < 3:
        mapped = _segment_cursor_from_page(page)
        if mapped is None:
            print("  ✅ Fin de segmentos Argenprop disponibles.")
            break

        slug, seg_page, seg_i = mapped
        segment = parse_segment_slug(slug)
        if not segment:
            page = _cursor_page_for_segment(seg_i + 1, 1)
            continue

        url = listing_url(segment, seg_page)
        referer = listing_url(segment, seg_page - 1) if seg_page > 1 else f"{BASE}/"
        print(f"  📄 Segmento {slug} (pág {seg_page}): {url}")

        html = await session.get_html(url, referer=referer)
        pages_visited += 1
        if session.waf_blocked:
            print("  ⛔ AWS WAF detectado — abortando.")
            break
        if not html:
            empty_streak += 1
            page = _cursor_page_for_segment(seg_i + 1, 1)
            continue

        listings = parse_listings_html(
            html,
            pagina_origen=page,
            tipo_hint=segment.tipo,
            op_hint=segment.op,
        )
        if not listings:
            page = _cursor_page_for_segment(seg_i + 1, 1)
            empty_streak = 0
            continue

        empty_streak = 0
        added = 0
        for item in listings:
            aid = item.get("argenprop_id")
            if aid and aid not in seen:
                seen.add(aid)
                results.append(item)
                added += 1
                if len(results) >= limit:
                    break

        print(f"  {slug} p{seg_page}: +{added} nuevas ({len(results)}/{limit})")

        total_ads = extract_total_from_html(html)
        if seg_page >= MAX_SAFE_PAGE or (total_ads and seg_page * 20 >= total_ads) or len(listings) < 12:
            page = _cursor_page_for_segment(seg_i + 1, 1)
        else:
            page += 1

        await asyncio.sleep(0.4)

    return {
        "listings": results,
        "next_page": page,
        "pages_visited": pages_visited,
        "waf_blocked": session.waf_blocked,
    }
