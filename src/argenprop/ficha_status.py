from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.argenprop.session import ApSession

logger = logging.getLogger("argenprop.ficha_status")


async def is_ficha_alive(session: ApSession, url: str) -> bool:
    """Verifica si una ficha individual de Argenprop sigue publicada (activa) o fue dada de baja (404)."""
    if not url:
        return False
    try:
        html = await session.get_html(url.strip())
        if not html:
            return False
        m_title = re.search(r"<title>(.*?)</title>", html, re.I)
        title = m_title.group(1).lower() if m_title else ""
        if "404" in title or "error" in title:
            return False
        if "no se encuentra disponible" in html.lower() or "aviso no disponible" in html.lower():
            return False
        return True
    except Exception as exc:
        logger.warning("Error comprobando ficha %s: %s", url, exc)
        return False


async def verify_ficha_urls(items: list[dict[str, str]], concurrency: int = 10) -> list[dict[str, Any]]:
    """
    Verifica una lista de URLs de Argenprop en paralelo.
    items: [{"zpId": "123", "url": "https://www.argenprop.com/..."}]
    Retorna: [{"zpId": "123", "alive": True/False, "status": 200/404}]
    """
    if not items:
        return []

    results: list[dict[str, Any]] = []
    session = ApSession()
    await session.init()
    sem = asyncio.Semaphore(concurrency)

    try:
        async def _check_one(it: dict[str, str]):
            aid = it.get("zpId") or it.get("argenprop_id") or ""
            url = it.get("url") or ""
            async with sem:
                alive = await is_ficha_alive(session, url)
                results.append({
                    "zpId": aid,
                    "argenprop_id": aid,
                    "url": url,
                    "alive": alive,
                    "status": 200 if alive else 404,
                })
                await asyncio.sleep(0.05)

        await asyncio.gather(*[_check_one(it) for it in items])
    finally:
        await session.close()

    return results
