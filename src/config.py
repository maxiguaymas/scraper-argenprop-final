from __future__ import annotations

from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ROOT = Path(__file__).resolve().parent.parent
_OFICIAL_ENV = _ROOT.parent / "remax-noa-oficial" / ".env"

_ENV_FILES: list[str] = []
if _OFICIAL_ENV.exists():
    _ENV_FILES.append(str(_OFICIAL_ENV))
_ENV_FILES.append(str(_ROOT / ".env"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=tuple(_ENV_FILES) if _ENV_FILES else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    database_url: str = (
        "postgresql+asyncpg://argenprop:argenprop@localhost:5434/argenprop"
    )

    # URL objetivo principal (Salta catálogo)
    argenprop_base_url: str = "https://www.argenprop.com"
    argenprop_start_url: str = (
        "https://www.argenprop.com/inmuebles/alquiler-o-venta/salta-arg"
    )

    # Supabase (opcional / CRM)
    supabase_url: str | None = Field(default=None, validation_alias="NEXT_PUBLIC_SUPABASE_URL")
    supabase_service_role_key: str | None = Field(
        default=None, validation_alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_anon_key: str | None = Field(
        default=None, validation_alias="NEXT_PUBLIC_SUPABASE_ANON"
    )

    request_delay: float = 1.2
    request_timeout: float = 35.0
    max_concurrent_requests: int = 3

    user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    # API Key para endpoints FastAPI / Railway
    api_key: str = Field(default="kX9mP2vL_argenprop_2026", validation_alias="API_KEY")

    # Scheduler cron y automatización Railway
    sync_interval_hours: int = Field(default=2, validation_alias="SYNC_INTERVAL_HOURS")
    run_on_startup: bool = Field(default=True, validation_alias="RUN_ON_STARTUP")
    catalog_limit: int = Field(default=10000, validation_alias="CATALOG_LIMIT")
    enrich_limit: int = Field(default=300, validation_alias="ENRICH_LIMIT")


settings = Settings()
