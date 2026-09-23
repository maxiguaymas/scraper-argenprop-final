import asyncio
import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional

from curl_cffi.requests import AsyncSession

from src.argenprop.urls import BASE
from src.config import settings

logger = logging.getLogger("argenprop")

_WAF_CACHE_FILE = Path(".waf_token.json")

FINGERPRINTS = [
    "chrome116",
    "chrome131",
    "chrome124",
    "chrome120",
    "chrome110",
    "edge101",
]


def load_cached_waf_token() -> str | None:
    if _WAF_CACHE_FILE.exists():
        try:
            data = json.loads(_WAF_CACHE_FILE.read_text())
            # Token válido por 3 horas (10800 segundos)
            if time.time() - data.get("timestamp", 0) < 10800:
                return data.get("token")
        except Exception:
            pass
    return None


def save_cached_waf_token(token: str) -> None:
    try:
        _WAF_CACHE_FILE.write_text(
            json.dumps({"token": token, "timestamp": time.time()})
        )
    except Exception:
        pass


_waf_lock: asyncio.Lock | None = None


async def solve_waf_with_nodriver(url: str = f"{BASE}/") -> str | None:
    """Resuelve el desafío de AWS WAF mediante nodriver y guarda la cookie aws-waf-token."""
    global _waf_lock
    if _waf_lock is None:
        _waf_lock = asyncio.Lock()

    async with _waf_lock:
        # Verificar si otro worker ya resolvió el token mientras esperábamos el lock
        cached = load_cached_waf_token()
        if cached:
            return cached

        try:
            import nodriver as uc
        except ImportError:
            logger.error("❌ nodriver no disponible para resolver AWS WAF")
            return None

        logger.info("🛡️ Resolviendo AWS WAF challenge con navegador automatizado...")
        browser = None
        try:
            # Siempre headless salvo que explícitamente se active HEADED_SCRAPER=1
            is_headed = bool(os.environ.get("HEADED_SCRAPER") == "1")
            chrome_bin = "/usr/bin/google-chrome" if Path("/usr/bin/google-chrome").exists() else None
            args = ["--window-size=600,400", "--disable-dev-shm-usage", "--no-sandbox"]
            if not is_headed:
                args.append("--disable-blink-features=AutomationControlled")

            browser = await uc.start(
                headless=not is_headed,
                browser_executable_path=chrome_bin,
                browser_args=args,
            )
            tab = await browser.get(url)

            token = None
            for _ in range(8):
                await asyncio.sleep(1.0)
                try:
                    raw = await tab.send(uc.cdp.network.get_all_cookies())
                    for c in raw:
                        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
                        val = getattr(c, "value", None) or (c.get("value") if isinstance(c, dict) else None)
                        if name == "aws-waf-token" and val:
                            token = val
                            break
                except Exception:
                    pass
                if token:
                    break

            if token:
                logger.info("✅ Token AWS WAF obtenido exitosamente (%s...)", token[:25])
                save_cached_waf_token(token)
                return token

            logger.warning("⚠️ No se pudo obtener la cookie aws-waf-token tras la espera")
            return None
        except Exception as exc:
            logger.error("❌ Error en solver WAF nodriver: %s", exc)
            return None
        finally:
            if browser:
                try:
                    browser.stop()
                except Exception:
                    pass


def is_waf_challenge(html: str) -> bool:
    if not html:
        return True
    low = html[:8000].lower()
    if "gokuprops" in low or "human verification" in low or "awswafintegration" in low or "challenge.js" in low:
        return True
    if "javascript is disabled" in low and len(html) < 8000:
        return True
    if "request blocked" in low or "access denied" in low:
        return True
    return False


def is_usable_argenprop_html(html: str) -> bool:
    if not html or len(html) < 4000:
        return False
    if is_waf_challenge(html):
        return False
    low = html.lower()
    return any(
        x in low
        for x in (
            "listing__item",
            "card-item",
            "listing-card",
            "data-item-card",
            "data-track-listing",
            "section-description",
            "data-open-gallery",
            "form-detail-phone-number",
            "details-phone-number",
        )
    )


class ApSession:
    """Sesión curl_cffi con TLS impersonate y evasión de AWS WAF."""

    def __init__(self) -> None:
        self.session: Optional[AsyncSession] = None
        self._ready = False
        self._current_fp = "chrome116"
        self._fp_index = 0
        self._last_request_time = 0.0
        self._waf_blocked = False

    @property
    def waf_blocked(self) -> bool:
        return self._waf_blocked

    def reset_waf_status(self) -> None:
        self._waf_blocked = False

    def _headers(self, referer: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,image/apng,*/*;q=0.8"
            ),
            "Accept-Language": "es-AR,es;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Cache-Control": "no-cache",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-User": "?1",
        }
        if referer:
            headers["Referer"] = referer
            headers["Sec-Fetch-Site"] = (
                "same-origin" if "argenprop.com" in referer else "cross-site"
            )
        else:
            headers["Sec-Fetch-Site"] = "none"
        return headers

    async def init(self, fingerprint: str | None = None) -> None:
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
        fp = fingerprint or self._current_fp
        self._current_fp = fp
        self.session = AsyncSession(
            impersonate=fp,
            timeout=settings.request_timeout,
            headers=self._headers(),
            max_redirects=5,
        )
        cached_token = load_cached_waf_token()
        if cached_token:
            self.session.cookies.set("aws-waf-token", cached_token, domain=".argenprop.com")
            logger.info("Cookie aws-waf-token cargada desde caché")
        self._ready = True
        logger.info("Sesión Argenprop inicializada (fp=%s)", fp)

    async def _rotate_fingerprint(self) -> str:
        self._fp_index = (self._fp_index + 1) % len(FINGERPRINTS)
        new_fp = FINGERPRINTS[self._fp_index]
        logger.info("Rotando fingerprint: %s -> %s", self._current_fp, new_fp)
        await self.init(new_fp)
        return new_fp

    async def get_html(self, url: str, referer: str | None = None) -> str | None:
        if self._waf_blocked:
            return None
        if not self._ready:
            await self.init()
        assert self.session is not None

        req_referer = referer or f"{BASE}/"
        attempts = 2

        for attempt in range(attempts):
            now = asyncio.get_running_loop().time()
            elapsed = now - self._last_request_time
            gap = settings.request_delay
            if elapsed < gap:
                await asyncio.sleep(gap - elapsed)

            self.session.headers.update(self._headers(req_referer))
            self._last_request_time = asyncio.get_running_loop().time()

            try:
                resp = await self.session.get(url, allow_redirects=True)
                html = resp.text or ""
            except Exception as exc:
                logger.warning("Error HTTP GET %s: %s", url[:80], exc)
                if attempt < attempts - 1:
                    await asyncio.sleep(random.uniform(0.5, 1.2))
                    continue
                return None

            if resp.status_code == 404:
                return html if html else "<html></html>"

            if resp.status_code in (202, 403) or is_waf_challenge(html):
                logger.warning(
                    "Aviso WAF (HTTP %s, %sb) — resolviendo token de AWS WAF...",
                    resp.status_code,
                    len(html),
                )
                token = await solve_waf_with_nodriver(url)
                if token:
                    self.session.cookies.set("aws-waf-token", token, domain=".argenprop.com")
                    self.session.cookies.set("aws-waf-token", token, domain=".sosiva451.com")
                    self._waf_blocked = False
                    try:
                        resp = await self.session.get(url, allow_redirects=True)
                        html = resp.text or ""
                        if resp.status_code == 200 and is_usable_argenprop_html(html):
                            return html
                    except Exception as exc:
                        logger.warning("Error reintentando tras resolver WAF: %s", exc)

                if attempt < attempts - 1:
                    await self._rotate_fingerprint()
                    await asyncio.sleep(random.uniform(1.8, 3.0))
                    continue
                self._waf_blocked = True
                return None

            if resp.status_code == 200 and is_usable_argenprop_html(html):
                self._waf_blocked = False
                return html

            if attempt < attempts - 1:
                await self._rotate_fingerprint()
                await asyncio.sleep(random.uniform(1.0, 2.0))

        return None

    async def get_json(self, url: str) -> dict | None:
        """Obtiene respuesta JSON (p. ej. api.sosiva451.com) usando la sesión con WAF bypass."""
        if self._waf_blocked:
            return None
        if not self._ready:
            await self.init()
        assert self.session is not None

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": "https://www.argenprop.com",
            "Referer": "https://www.argenprop.com/",
        }

        try:
            resp = await self.session.get(url, headers=headers, allow_redirects=True)
            if resp.status_code == 200:
                return resp.json()
        except Exception as exc:
            logger.debug("Error get_json %s: %s", url, exc)
        return None

    async def close(self) -> None:
        if self.session:
            try:
                await self.session.close()
            except Exception:
                pass
            self.session = None
            self._ready = False
