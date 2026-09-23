from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.mapper import to_property_dict
from src.db.models import ArgenpropProperty

logger = logging.getLogger("argenprop")


async def upsert_property(
    session: AsyncSession,
    prop_data: dict[str, Any],
    scrape_time: datetime,
) -> tuple[ArgenpropProperty, bool]:
    """Inserta o actualiza una propiedad en argenprop_properties vía PostgreSQL ON CONFLICT."""
    record = to_property_dict(prop_data, now=scrape_time)
    aid = record["argenprop_id"]

    stmt = insert(ArgenpropProperty).values(**record)

    update_cols = {
        col: stmt.excluded[col]
        for col in record
        if col not in ("id", "argenprop_id", "primera_vez_visto", "created_at")
    }
    update_cols["activa"] = True
    update_cols["ultima_actualizacion"] = scrape_time
    update_cols["updated_at"] = scrape_time

    # Conservar campos enriquecidos existentes si el listado viene sin ellos
    stmt = stmt.on_conflict_do_update(
        index_elements=["argenprop_id"],
        set_=update_cols,
    ).returning(ArgenpropProperty)

    result = await session.execute(stmt)
    obj = result.scalar_one()
    return obj, True


async def mark_inactive_before(session: AsyncSession, cutoff: datetime) -> int:
    """Marca como inactivas propiedades no vistas en el scrape actual."""
    stmt = (
        update(ArgenpropProperty)
        .where(
            ArgenpropProperty.activa.is_(True),
            ArgenpropProperty.ultima_actualizacion < cutoff,
        )
        .values(
            activa=False,
            updated_at=cutoff,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount


async def get_stats(session: AsyncSession) -> dict[str, int]:
    """Estadísticas de la base de datos de Argenprop."""
    total_q = select(func.count(ArgenpropProperty.id))
    active_q = select(func.count(ArgenpropProperty.id)).where(ArgenpropProperty.activa.is_(True))
    inactive_q = select(func.count(ArgenpropProperty.id)).where(ArgenpropProperty.activa.is_(False))

    total = (await session.execute(total_q)).scalar_one()
    active = (await session.execute(active_q)).scalar_one()
    inactive = (await session.execute(inactive_q)).scalar_one()

    return {"total": total, "active": active, "inactive": inactive}


async def get_missing_enrich(session: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
    """Obtiene avisos activos a los que les falte latitud o teléfono para enriquecer."""
    stmt = (
        select(
            ArgenpropProperty.argenprop_id,
            ArgenpropProperty.url,
            ArgenpropProperty.latitud,
            ArgenpropProperty.anunciante_telefono,
        )
        .where(
            ArgenpropProperty.activa.is_(True),
            ArgenpropProperty.url.isnot(None),
            (
                ArgenpropProperty.latitud.is_(None)
                | ArgenpropProperty.anunciante_telefono.is_(None)
                | ArgenpropProperty.fecha_publicacion.is_(None)
            ),
        )
        .order_by(ArgenpropProperty.updated_at.desc())
        .limit(limit)
    )
    res = await session.execute(stmt)
    return [
        {
            "argenprop_id": r.argenprop_id,
            "url": r.url,
            "missing_coords": r.latitud is None,
            "missing_phone": r.anunciante_telefono is None,
        }
        for r in res.all()
    ]


async def update_enriched(
    session: AsyncSession,
    argenprop_id: str,
    fields: dict[str, Any],
    now: datetime,
) -> None:
    """Actualiza datos enriquecidos de una ficha."""
    if not fields:
        return
    fields["updated_at"] = now
    stmt = (
        update(ArgenpropProperty)
        .where(ArgenpropProperty.argenprop_id == argenprop_id)
        .values(**fields)
    )
    await session.execute(stmt)
