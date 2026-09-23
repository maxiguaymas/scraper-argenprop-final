from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from src.config import settings


class SupabaseError(Exception):
    def __init__(self, message: str, status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


def _require_credentials() -> tuple[str, str]:
    base = (settings.supabase_url or "").strip().rstrip("/")
    key = (settings.supabase_service_role_key or "").strip()
    if not base or not key:
        raise SupabaseError("Faltan NEXT_PUBLIC_SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY")
    return base, key


def _request(
    method: str,
    path: str,
    body: Any = None,
    params: dict[str, str] | None = None,
    prefer: str | None = None,
    timeout: float = 30.0,
) -> Any:
    base, key = _require_credentials()
    rel = path.lstrip("/")
    url = f"{base}/rest/v1/{rel}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Content-Type", "application/json")
    if prefer:
        req.add_header("Prefer", prefer)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if not raw:
                return None
            return json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise SupabaseError(
            f"Supabase HTTP {exc.code} {exc.reason}: {err_body[:500]}",
            status=exc.code,
            body=err_body,
        ) from exc
    except Exception as exc:
        raise SupabaseError(f"Supabase request failed: {exc}") from exc


def get_table() -> str:
    return "argenprop_propiedades"


def get_by_argenprop_id(argenprop_id: str) -> dict[str, Any] | None:
    rows = _request(
        "GET",
        get_table(),
        params={
            "select": "id,url,titulo,precio,moneda,latitud,longitud,activa,anunciante_telefono",
            "argenprop_id": f"eq.{argenprop_id}",
            "limit": "1",
        },
    )
    return rows[0] if isinstance(rows, list) and rows else None


def insert_property(record: dict[str, Any]) -> dict[str, Any]:
    rows = _request(
        "POST",
        get_table(),
        body=record,
        prefer="return=representation",
    )
    return {"ok": True, "action": "inserted", "row": rows[0] if rows else None}


def update_property(row_id: int, record: dict[str, Any]) -> dict[str, Any]:
    rows = _request(
        "PATCH",
        get_table(),
        body=record,
        params={"id": f"eq.{row_id}"},
        prefer="return=representation",
    )
    return {"ok": True, "action": "updated", "row": rows[0] if rows else None}


def count_active() -> int:
    base, key = _require_credentials()
    url = f"{base}/rest/v1/{get_table()}?select=id&activa=eq.true&limit=1"
    req = urllib.request.Request(url, method="HEAD")
    req.add_header("apikey", key)
    req.add_header("Authorization", f"Bearer {key}")
    req.add_header("Prefer", "count=exact")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_range = resp.headers.get("content-range") or ""
            if "/" in content_range:
                total = content_range.split("/")[-1]
                return int(total) if total.isdigit() else 0
    except Exception:
        pass
    return 0


def get_missing_enrich_supabase(limit: int = 50) -> list[dict[str, Any]]:
    """Obtiene propiedades de Supabase que carecen de coordenadas y enriquecimiento de ficha."""
    rows = _request(
        "GET",
        get_table(),
        params={
            "select": "id,argenprop_id,url,titulo",
            "coordenadas_origen": "is.null",
            "activa": "eq.true",
            "limit": str(limit),
        },
    )
    return rows if isinstance(rows, list) else []


def upsert_batch_properties(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Upsert masivo eficiente de propiedades en Supabase usando on_conflict=argenprop_id."""
    if not records:
        return {"ok": True, "count": 0}
    _request(
        "POST",
        get_table(),
        body=records,
        params={"on_conflict": "argenprop_id"},
        prefer="resolution=merge-duplicates,return=minimal",
    )
    return {"ok": True, "count": len(records)}


def get_all_active_ids() -> list[dict[str, Any]]:
    """Obtiene id, argenprop_id y url de todas las propiedades actualmente activas en Supabase."""
    all_rows: list[dict[str, Any]] = []
    limit = 1000
    offset = 0
    while True:
        rows = _request(
            "GET",
            get_table(),
            params={
                "select": "id,argenprop_id,url",
                "activa": "eq.true",
                "limit": str(limit),
                "offset": str(offset),
            },
        )
        if not rows or not isinstance(rows, list):
            break
        all_rows.extend(rows)
        offset += limit
        if len(rows) < limit:
            break
    return all_rows


def mark_delisted_batch(argenprop_ids: list[str], reason: str = "despublicada_en_argenprop") -> int:
    """Marca propiedades como inactivas (baja) de forma masiva sin borrarlas."""
    if not argenprop_ids:
        return 0
    from datetime import UTC, datetime
    now = datetime.now(UTC).isoformat()
    chunk_size = 100
    updated_total = 0
    for i in range(0, len(argenprop_ids), chunk_size):
        chunk = argenprop_ids[i:i + chunk_size]
        ids_str = ",".join(chunk)
        _request(
            "PATCH",
            get_table(),
            body={"activa": False, "fecha_baja": now, "motivo_baja": reason, "updated_at": now},
            params={"argenprop_id": f"in.({ids_str})"},
            prefer="return=minimal",
        )
        updated_total += len(chunk)
    return updated_total

