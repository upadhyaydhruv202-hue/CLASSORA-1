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
_AVAIL = {}


def _now():
    return datetime.now(timezone.utc).isoformat()


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
    tmp.replace(_PATH)


def available(table: str) -> bool:
    if not is_supabase_configured():
        return table not in _CLOUD_ONLY
    if table in _AVAIL:
        return _AVAIL[table]
    try:
        supabase.table(table).select("*").limit(1).execute()
        _AVAIL[table] = True
    except Exception:
        _AVAIL[table] = False
    return _AVAIL[table]


def insert(table: str, row: dict):
    if row.get("student_id") is not None:
        try:
            if int(row["student_id"]) < 0:
                return None
        except (TypeError, ValueError):
            pass
    if is_supabase_configured():
        if not available(table):
            return None
        try:
            return supabase.table(table).insert(row).execute().data
        except Exception:
            return None
    if table in _CLOUD_ONLY:
        return None
    with _LOCK:
        data = _load()
        data.setdefault("tables", {}).setdefault(table, [])
        data.setdefault("seq", {})
        payload = deepcopy(row)
        payload.setdefault("id", int(data["seq"].get(table, 1)))
        data["seq"][table] = int(payload["id"]) + 1
        payload.setdefault("created_at", _now())
        data["tables"][table].append(payload)
        _dump(data)
        return [payload]


def select(table: str, **eq):
    if is_supabase_configured():
        if not available(table):
            return []
        try:
            q = supabase.table(table).select("*")
            for k, v in eq.items():
                q = q.eq(k, v)
            return q.execute().data or []
        except Exception:
            return []
    if table in _CLOUD_ONLY:
        return []
    rows = list((_load().get("tables") or {}).get(table) or [])
    if not eq:
        return rows
    out = []
    for row in rows:
        if all(row.get(k) == v for k, v in eq.items()):
            out.append(row)
    return out


def update(table: str, match: dict, values: dict):
    if is_supabase_configured():
        if not available(table):
            return None
        try:
            q = supabase.table(table).update(values)
            for k, v in match.items():
                q = q.eq(k, v)
            return q.execute().data
        except Exception:
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
