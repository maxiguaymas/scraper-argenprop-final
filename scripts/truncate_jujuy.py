import sys
from pathlib import Path

# Add project root to sys.path
root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))

from src.argenprop.region import use_region
from src.db.supabase_client import _request, count_active, get_table

with use_region("jujuy") as cfg:
    print(f"🗑️ Vaciando tabla de Jujuy: {cfg.table} ({cfg.provincia})...")
    before = count_active()
    print(f"  • Cantidad antes del vaciado: {before}")
    
    try:
        res = _request(
            "DELETE",
            cfg.table,
            params={"id": "gt.0"},
            prefer="return=minimal",
        )
        print("  ✅ Solicitud DELETE enviada con éxito.")
    except Exception as exc:
        print(f"  ⚠️ Error en DELETE con id: {exc}, probando con argenprop_id...")
        try:
            res = _request(
                "DELETE",
                cfg.table,
                params={"argenprop_id": "neq.empty"},
                prefer="return=minimal",
            )
            print("  ✅ Solicitud DELETE alternativa enviada con éxito.")
        except Exception as exc2:
            print(f"  ❌ Error eliminando registros: {exc2}")
            sys.exit(1)

    after = count_active()
    print(f"  • Cantidad después del vaciado: {after}")
    if after == 0:
        print("🎉 Tabla argenprop_propiedades_jujuy vaciada al 100% (0 propiedades).")
    else:
        print(f"⚠️ Aún quedan {after} propiedades en la tabla.")
