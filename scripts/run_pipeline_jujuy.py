import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.services.supabase_sync import run_full_production_pipeline


async def main():
    print("🚀 Disparando Pipeline Completo de Producción para JUJUY...")
    summary = await run_full_production_pipeline(
        limit=10000,
        enrich_limit=1000,
        verify_bajas=True,
        region="jujuy",
    )
    print("\n📋 Resumen final:", summary)


if __name__ == "__main__":
    asyncio.run(main())
