#!/usr/bin/env python3
from __future__ import annotations
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.db.supabase_client import _request

def reset_table(batch_size: int = 500) -> int:
    print("\n⚠️ [RESET SUPABASE] Iniciando vaciado de la tabla argenprop_propiedades...")
    deleted_total = 0
    while True:
        rows = _request(
            "GET",
            "argenprop_propiedades",
            params={"select": "id", "limit": str(batch_size)},
        )
        if not rows or not isinstance(rows, list):
            break
        ids_str = ",".join(str(r["id"]) for r in rows)
        _request("DELETE", "argenprop_propiedades", params={"id": f"in.({ids_str})"})
        deleted_total += len(rows)
        print(f"  🗑️ Borradas {deleted_total} propiedades acumuladas...")
        time.sleep(0.1)

    print(f"\n✅ Vaciado completado: {deleted_total} registros eliminados.")
    print("✨ La tabla argenprop_propiedades quedó en 0 registros.")
    return deleted_total

if __name__ == "__main__":
    reset_table()
