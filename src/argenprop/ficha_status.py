from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from src.argenprop.session import ApSession

logger = logging.getLogger("argenprop.ficha_status")


async def is_ficha_alive(session: ApSession, aid: str, url: str | None = None) -> bool:
    """Verifica si una ficha individual de Argenprop sigue publicada (activa) o fue dada de baja (410/404)."""
    target = f"https://www.argenprop.com/propiedad--{aid}" if aid else (url or "")
    if not target:
        return False
    try:
        assert session.session is not None
        headers = {"Referer": "https://www.argenprop.com/"}
        resp = await session.session.get(target, headers=headers, allow_redirects=True)
        code = resp.status_code
        if code in (404, 410):
            return False
        if code == 200:
            text = (resp.text or "").lower()
            if "no se encuentra disponible" in text or "aviso no disponible" in text:
                return False
            return True
        return True
    except Exception as exc:
        logger.warning("Error comprobando ficha %s: %s", target, exc)
        return True


async def verify_ficha_urls(items: list[dict[str, str]], concurrency: int = 4) -> list[dict[str, Any]]:
    """
    Verifica una lista de URLs de Argenprop en paralelo de forma segura.
    items: [{"zpId": "123", "url": "https://www.argenprop.com/..."}]
    Retorna: [{"zpId": "123", "alive": True/False, "status": 200/410}]
    """
    if not items:
        return []

    results: list[dict[str, Any]] = []
    session = ApSession()
    await session.init(auto_warmup=False)
    sem = asyncio.Semaphore(concurrency)

    try:
        async def _check_one(it: dict[str, str]):
            aid = str(it.get("zpId") or it.get("argenprop_id") or "")
            url = it.get("url") or ""
            async with sem:
                alive = await is_ficha_alive(session, aid, url)
                results.append({
                    "zpId": aid,
                    "argenprop_id": aid,
                    "url": url,
                    "alive": alive,
                    "status": 200 if alive else 410,
                })
                await asyncio.sleep(0.2)

        await asyncio.gather(*[_check_one(it) for it in items])
    finally:
        await session.close()

    return results

