from __future__ import annotations

import asyncio
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.services.supabase_sync import run_full_production_pipeline

logger = logging.getLogger("argenprop.scheduler")


async def start_scheduler_blocking() -> None:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_full_production_pipeline,
        trigger=IntervalTrigger(hours=settings.sync_interval_hours),
        id="argenprop_sync_job",
        name=f"Argenprop {settings.sync_interval_hours}h Pipeline",
        replace_existing=True,
    )
    scheduler.start()
    print(f"⏰ Scheduler iniciado: pipeline programado cada {settings.sync_interval_hours} horas.")

    # Ejecutar sync inicial tras 5 segundos
    await asyncio.sleep(5)
    await run_full_production_pipeline(limit=settings.catalog_limit, enrich_limit=settings.enrich_limit)

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        print("Scheduler detenido.")
