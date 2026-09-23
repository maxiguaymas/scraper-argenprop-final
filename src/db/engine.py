from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from src.config import settings

async_engine = create_async_engine(
    settings.database_url,
    pool_size=10,
    max_overflow=20,
    pool_recycle=300,
    echo=False,
)

async_session_factory = async_sessionmaker(
    bind=async_engine,
    expire_on_commit=False,
)

# Sesión sincrónica para Streamlit / Alembic
_sync_url = settings.database_url.replace(
    "postgresql+asyncpg://", "postgresql+psycopg2://"
)
sync_engine = create_engine(
    _sync_url,
    pool_size=5,
    max_overflow=10,
    pool_recycle=300,
    echo=False,
)

SyncSession = sessionmaker(bind=sync_engine, expire_on_commit=False)
