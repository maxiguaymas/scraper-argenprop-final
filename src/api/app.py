from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
from typing import Any

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from src.config import settings
from src.services.supabase_sync import (
    run_full_production_pipeline,
    run_supabase_enrich,
    run_supabase_scrape,
)

logger = logging.getLogger("argenprop_api")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

_pipeline_lock = asyncio.Lock()
_pipeline_started_at: datetime | None = None
_last_pipeline_run: datetime | None = None
_last_pipeline_summary: dict[str, Any] | None = None
_scheduler: AsyncIOScheduler | None = None


async def _execute_pipeline_task() -> dict[str, Any]:
    global _pipeline_started_at, _last_pipeline_run, _last_pipeline_summary
    if _pipeline_lock.locked():
        logger.warning("Pipeline ya en ejecución — omitiendo disparo concurrente.")
        return {"ok": False, "detail": "pipeline_in_progress"}

    async with _pipeline_lock:
        _pipeline_started_at = datetime.now(UTC)
        logger.info("⏰ Iniciando pipeline Argenprop (cada %s horas)...", settings.sync_interval_hours)
        try:
            summary = await run_full_production_pipeline(
                limit=settings.catalog_limit,
                enrich_limit=settings.enrich_limit,
                verify_bajas=True,
            )
            _last_pipeline_summary = summary
            _last_pipeline_run = datetime.now(UTC)
            logger.info("✅ Pipeline de producción finalizado con éxito.")
            return summary
        except Exception as exc:
            logger.exception("❌ Error ejecutando pipeline de producción: %s", exc)
            return {"ok": False, "error": str(exc)}
        finally:
            _pipeline_started_at = None


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _scheduler
    logger.info("🚀 Argenprop Scraper API iniciando...")

    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        _execute_pipeline_task,
        trigger=IntervalTrigger(hours=settings.sync_interval_hours),
        id="argenprop_2h_pipeline",
        name=f"Argenprop {settings.sync_interval_hours}h Pipeline",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("⏰ Scheduler iniciado: sincronización programada cada %s horas.", settings.sync_interval_hours)

    if settings.run_on_startup:
        async def _delayed_startup():
            await asyncio.sleep(15)  # Permite que FastAPI enlace el puerto $PORT y responda a Railway health
            logger.info("🚀 Ejecutando sincronización inicial de arranque...")
            await _execute_pipeline_task()

        asyncio.create_task(_delayed_startup())

    yield

    if _scheduler and _scheduler.running:
        _scheduler.shutdown()
        logger.info("🛑 Scheduler detenido.")
    logger.info("🛑 Argenprop Scraper API finalizada.")


app = FastAPI(
    title="Argenprop Scraper API",
    version="1.0.0",
    lifespan=lifespan,
)


async def verify_api_key(x_api_key: str | None = Header(default=None, alias="x-api-key")) -> str:
    expected = (settings.api_key or "").strip()
    if not expected:
        raise HTTPException(status_code=500, detail="API_KEY no configurada")
    if not x_api_key or x_api_key != expected:
        raise HTTPException(status_code=401, detail="API key inválida")
    return x_api_key


class VerifyFichaItem(BaseModel):
    zpId: str = ""
    url: str = ""


class VerifyFichasRequest(BaseModel):
    items: list[VerifyFichaItem] = Field(default_factory=list)


class ScrapeRequest(BaseModel):
    url: str | None = None
    limit: int = Field(default=100, ge=1, le=10000)
    segmented: bool = True


class EnrichRequest(BaseModel):
    limit: int = Field(default=50, ge=1, le=500)


@app.get("/health")
async def health() -> dict[str, Any]:
    next_run = None
    if _scheduler:
        job = _scheduler.get_job("argenprop_2h_pipeline")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()

    return {
        "status": "ok",
        "service": "argenprop-scraper",
        "timestamp": datetime.now(UTC).isoformat(),
        "pipeline_running": _pipeline_lock.locked(),
        "pipeline_started_at": _pipeline_started_at.isoformat() if _pipeline_started_at else None,
        "last_pipeline_run": _last_pipeline_run.isoformat() if _last_pipeline_run else None,
        "next_scheduled_run": next_run,
        "sync_interval_hours": settings.sync_interval_hours,
        "supabase_configured": bool(settings.supabase_url and settings.supabase_service_role_key),
        "verify_fichas": True,
    }


@app.get("/", dependencies=[Depends(verify_api_key)])
async def root() -> dict[str, Any]:
    return {
        "service": "Argenprop-Scraper API",
        "engine": "curl_cffi + nodriver + supabase + cross-matcher",
        "interval_hours": settings.sync_interval_hours,
        "endpoints": [
            "/pipeline/run",
            "/verify/fichas",
            "/scrape/supabase",
            "/enrich/supabase",
            "/match/run",
            "/match/stats",
        ],
        "pipeline_running": _pipeline_lock.locked(),
        "last_pipeline_summary": _last_pipeline_summary,
    }


@app.post("/pipeline/run", dependencies=[Depends(verify_api_key)])
async def trigger_pipeline() -> dict[str, Any]:
    """Dispara el pipeline completo bajo demanda (Scrape + Bajas + Enrich + Match Supabase)."""
    if _pipeline_lock.locked():
        raise HTTPException(status_code=409, detail="Pipeline ya en ejecución")
    res = await _execute_pipeline_task()
    return {"ok": True, "result": res}


@app.post("/verify/fichas", dependencies=[Depends(verify_api_key)])
async def verify_fichas(req: VerifyFichasRequest) -> dict[str, Any]:
    """Chequea si las fichas de Argenprop siguen publicadas (aviso vivo vs 404/baja)."""
    from src.argenprop.ficha_status import verify_ficha_urls

    items = [
        {"zpId": (it.zpId or "").strip(), "url": (it.url or "").strip()}
        for it in (req.items or [])
        if (it.zpId or "").strip() and (it.url or "").strip()
    ][:60]
    if not items:
        return {"ok": True, "results": []}
    results = await verify_ficha_urls(items)
    return {"ok": True, "results": results}


@app.post("/match/run", dependencies=[Depends(verify_api_key)])
async def trigger_match_persistence() -> dict[str, Any]:
    """Ejecuta el cruce inteligente Argenprop vs Zonaprop y persiste en Supabase."""
    from src.services.cross_matcher import persist_cross_matches_to_supabase

    res = await asyncio.to_thread(persist_cross_matches_to_supabase)
    return {"ok": True, "result": res}


@app.get("/match/stats", dependencies=[Depends(verify_api_key)])
async def get_match_stats(limit_ap: int | None = None) -> dict[str, Any]:
    """Devuelve las métricas y estadísticas del cruce Argenprop vs Zonaprop."""
    from src.services.cross_matcher import analyze_cross_market

    res = analyze_cross_market(limit_ap=limit_ap)
    return {
        "total_argenprop": res["total_argenprop"],
        "total_zonaprop_analizadas": res["total_zonaprop_analizadas"],
        "exclusivas_argenprop": res["exclusivas_argenprop_count"],
        "porcentaje_exclusividad_argenprop": res["porcentaje_exclusividad_argenprop"],
        "compartidas_ambos_portales": res["compartidas_count"],
        "ejemplos_compartidas": res["compartidas"][:5],
    }


@app.post("/scrape/supabase", dependencies=[Depends(verify_api_key)])
@app.post("/scrape/argenprop/supabase", dependencies=[Depends(verify_api_key)])
async def trigger_supabase_scrape(req: ScrapeRequest) -> dict[str, Any]:
    if _pipeline_lock.locked():
        raise HTTPException(status_code=409, detail="Proceso en curso")
    async with _pipeline_lock:
        res = await run_supabase_scrape(url=req.url, limit=req.limit, segmented=req.segmented)
        return res


@app.post("/enrich/supabase", dependencies=[Depends(verify_api_key)])
async def trigger_supabase_enrich(req: EnrichRequest) -> dict[str, Any]:
    if _pipeline_lock.locked():
        raise HTTPException(status_code=409, detail="Proceso en curso")
    async with _pipeline_lock:
        res = await run_supabase_enrich(limit=req.limit)
        return res
