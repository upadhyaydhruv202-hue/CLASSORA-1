"""Graceful persistence for the Student Success layer. Never writes demo IDs (<0) to production."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from src.database.config import is_supabase_configured, supabase

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[2] / "data" / "success_store.json"
_CLOUD_ONLY = {"mentorships", "complaints", "student_moderation_status", "mentorship_messages", "appeals"}
_ACADEMIC = {
    "academic_resource_sources",
    "academic_resource_types",
    "academic_resource_subjects",
    "academic_resources",
    "academic_resource_reports",
}
_AVAIL = {}
_LAST_ERROR = {}


def _local_ok(table: str) -> bool:
    return table not in _CLOUD_ONLY


def _academic_fallback(table: str) -> bool:
    return table in _ACADEMIC and _local_ok(table)


def _now():
    return datetime.now(timezone.utc).isoformat()


def last_error(table: str) -> str:
    return str(_LAST_ERROR.get(table) or "")


def _empty():
    return {"seq": {}, "tables": {}}


def _load():
    if not _PATH.exists():
        return _empty()
    with _PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _dump(data):
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        tmp.replace(_PATH)
    except PermissionError:
        # Windows can briefly lock the target; write directly as a fallback.
        _PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def available(table: str) -> bool:
    if not is_supabase_configured():
        return _local_ok(table)
    if _AVAIL.get(table) is True:
        return True
    try:
        supabase.table(table).select("*").limit(1).execute()
        _AVAIL[table] = True
        _LAST_ERROR.pop(table, None)
        return True
    except Exception as exc:
        _LAST_ERROR[table] = str(exc)
        _AVAIL[table] = False
        return _academic_fallback(table)


def insert(table: str, row: dict):
    if row.get("student_id") is not None:
        try:
            if int(row["student_id"]) < 0:
                return None
        except (TypeError, ValueError):
            pass
    payload = deepcopy(row)
    if is_supabase_configured():
        try:
            data = supabase.table(table).insert(payload).execute().data
            _AVAIL[table] = True
            _LAST_ERROR.pop(table, None)
            return data
        except Exception as exc:
            message = str(exc)
            _LAST_ERROR[table] = message
            # Unknown-column errors are schema drift, not a missing table — retry without those fields.
            if "PGRST204" in message or "schema cache" in message.lower():
                cleaned = dict(payload)
                for key in list(cleaned):
                    if key in message or f"'{key}'" in message:
                        cleaned.pop(key, None)
                # Common additive columns that may be absent on older SQL.
                for optional in ("discovery_status", "organization", "section", "logo_url", "thumbnail_url"):
                    if optional in message:
                        cleaned.pop(optional, None)
                if cleaned != payload:
                    try:
                        data = supabase.table(table).insert(cleaned).execute().data
                        _AVAIL[table] = True
                        return data
                    except Exception as retry_exc:
                        _LAST_ERROR[table] = str(retry_exc)
                        message = str(retry_exc)
            # Only fall back locally when the table itself is missing.
            missing = "PGRST205" in message or "could not find the table" in message.lower()
            if missing and _academic_fallback(table):
                _AVAIL[table] = False
            else:
                if "PGRST205" in message or "could not find the table" in message.lower():
                    _AVAIL[table] = False
                return None
    if table in _CLOUD_ONLY:
        return None
    if is_supabase_configured() and not _academic_fallback(table):
        return None
    with _LOCK:
        data = _load()
        data.setdefault("tables", {}).setdefault(table, [])
        data.setdefault("seq", {})
        local_row = deepcopy(payload)
        local_row.setdefault("id", int(data["seq"].get(table, 1)))
        data["seq"][table] = int(local_row["id"]) + 1
        local_row.setdefault("created_at", _now())
        data["tables"][table].append(local_row)
        _dump(data)
        return [local_row]


def select(table: str, **eq):
    if is_supabase_configured() and _AVAIL.get(table) is not False:
        try:
            rows = []
            start = 0
            page_size = 1000
            while True:
                q = supabase.table(table).select("*")
                for k, v in eq.items():
                    q = q.eq(k, v)
                q = q.range(start, start + page_size - 1)
                batch = q.execute().data or []
                rows.extend(batch)
                if len(batch) < page_size:
                    break
                start += page_size
            _AVAIL[table] = True
            _LAST_ERROR.pop(table, None)
            return rows
        except Exception as exc:
            message = str(exc)
            _LAST_ERROR[table] = message
            missing = "PGRST205" in message or "could not find the table" in message.lower()
            if missing:
                _AVAIL[table] = False
                if not _academic_fallback(table):
                    return []
            else:
                return []
    if table in _CLOUD_ONLY:
        return []
    # Local file fallback only when Supabase is off or the academic table is missing.
    if is_supabase_configured() and _AVAIL.get(table) is not False:
        return []
    rows = list((_load().get("tables") or {}).get(table) or [])
    if not eq:
        return rows
    return [row for row in rows if all(row.get(k) == v for k, v in eq.items())]


def update(table: str, match: dict, values: dict):
    if is_supabase_configured() and _AVAIL.get(table) is not False:
        try:
            q = supabase.table(table).update(values)
            for k, v in match.items():
                q = q.eq(k, v)
            data = q.execute().data
            _AVAIL[table] = True
            _LAST_ERROR.pop(table, None)
            return data
        except Exception as exc:
            _LAST_ERROR[table] = str(exc)
            _AVAIL[table] = False
            if not _academic_fallback(table):
                return None
    if table in _CLOUD_ONLY:
        return None
    with _LOCK:
        data = _load()
        rows = data.setdefault("tables", {}).setdefault(table, [])
        changed = []
        for row in rows:
            if all(row.get(k) == v for k, v in match.items()):
                row.update(values)
                changed.append(row)
        _dump(data)
        return changed
