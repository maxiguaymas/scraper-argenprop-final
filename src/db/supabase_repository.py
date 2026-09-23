from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.db import supabase_client as sb
from src.db.mapper import to_supabase_record


def save_to_supabase(prop: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
    aid = str(prop.get("argenprop_id") or "")
    if not aid:
        return {"ok": False, "error": "missing argenprop_id"}

    ts = now or datetime.now(UTC)

    try:
        existing = sb.get_by_argenprop_id(aid)
        if existing:
            record = to_supabase_record(prop, now=ts, is_insert=False)
            res = sb.update_property(existing["id"], record)
            return {"ok": True, "action": "updated", "argenprop_id": aid}

        record = to_supabase_record(prop, now=ts, is_insert=True)
        res = sb.insert_property(record)
        return {"ok": True, "action": "inserted", "argenprop_id": aid}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "argenprop_id": aid}


def save_batch_supabase(properties: list[dict[str, Any]], chunk_size: int = 100) -> dict[str, int]:
    now = datetime.now(UTC)
    results = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}
    if not properties:
        return results

    records = [to_supabase_record(p, now=now, is_insert=True) for p in properties]

    for i in range(0, len(records), chunk_size):
        chunk = records[i:i + chunk_size]
        try:
            sb.upsert_batch_properties(chunk)
            results["updated"] += len(chunk)
        except Exception as exc:
            print(f"⚠️ Error en batch upsert ({exc}), ejecutando fallback individual...")
            for r in chunk:
                try:
                    aid = r.get("argenprop_id")
                    existing = sb.get_by_argenprop_id(aid)
                    if existing:
                        sb.update_property(existing["id"], r)
                        results["updated"] += 1
                    else:
                        sb.insert_property(r)
                        results["inserted"] += 1
                except Exception:
                    results["errors"] += 1

    return results
