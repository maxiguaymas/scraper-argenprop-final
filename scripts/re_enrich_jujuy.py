import asyncio
import sys
from pathlib import Path
from datetime import datetime, UTC

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.argenprop.region import use_region
from src.argenprop.session import ApSession
from src.argenprop.detail_enricher import enrich_single_listing
from src.db.supabase_client import _request, update_property
from src.db.mapper import to_supabase_record

async def main():
    with use_region("jujuy") as cfg:
        print(f"🔄 Re-enriqueciendo propiedades de Jujuy ({cfg.table}) con fechas y visualizaciones...")
        rows = _request("GET", cfg.table, params={"select": "id,argenprop_id,url", "limit": "200"})
        print(f"Total a enriquecer: {len(rows)}")
        
        session = ApSession()
        await session.init()
        sem = asyncio.Semaphore(10)
        enriched = 0
        errors = 0
        now = datetime.now(UTC)
        
        async def _one(r):
            nonlocal enriched, errors
            aid = r["argenprop_id"]
            url = r["url"]
            row_id = r["id"]
            async with sem:
                try:
                    fields = await enrich_single_listing(session, url, aid)
                    if fields:
                        fields["argenprop_id"] = aid
                        rec = to_supabase_record(fields, now=now, is_insert=False)
                        await asyncio.to_thread(update_property, row_id, rec)
                        enriched += 1
                except Exception as e:
                    print(f"Error {aid}: {e}")
                    errors += 1
                await asyncio.sleep(0.05)
                
        chunk_size = 40
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i:i+chunk_size]
            await asyncio.gather(*[_one(r) for r in chunk])
            print(f"  ...procesadas {enriched}/{len(rows)}")
            
        await session.close()
        print(f"✅ Finalizado: {enriched} actualizadas, {errors} errores.")

if __name__ == "__main__":
    asyncio.run(main())
