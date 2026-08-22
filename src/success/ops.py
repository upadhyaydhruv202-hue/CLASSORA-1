"""Helpers for existing Success Hub ops: reports, search, and CSV import."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone


def build_report(profiles=None, cases=None, alerts=None, appointments=None, academic=None, lms=None, outcomes=None):
    profiles = profiles or []
    cases = cases or []
    alerts = alerts or []
    appointments = appointments or []
    academic = academic or []
    lms = lms or []
    outcomes = outcomes or []
    bands = {}
    for profile in profiles:
        cat = (profile.get("prediction") or {}).get("category") or "Unknown"
        bands[cat] = bands.get(cat, 0) + 1
    rates = []
    for profile in profiles:
        rate = (profile.get("attendance") or {}).get("rate")
        if rate is None:
            continue
        try:
            rates.append(float(rate))
        except (TypeError, ValueError):
            continue
    open_cases = [row for row in cases if str(row.get("status") or "open").lower() in ("open", "pending")]
    requested = [row for row in appointments if str(row.get("status") or "").lower() == "requested"]
    return {
        "student_count": len(profiles),
        "high_critical": sum(
            1 for p in profiles if (p.get("prediction") or {}).get("category") in ("High", "Critical")
        ),
        "avg_attendance": round(sum(rates) / len(rates), 1) if rates else None,
        "open_cases": len(open_cases),
        "closed_cases": max(0, len(cases) - len(open_cases)),
        "alerts": len(alerts),
        "appointments": len(appointments),
        "appointments_requested": len(requested),
        "academic_records": len(academic),
        "lms_events": len(lms),
        "outcomes": len(outcomes),
        "bands": bands,
    }


def search_profiles(profiles, q=""):
    needle = (q or "").strip().lower()
    rows = profiles or []
    if not needle:
        return list(rows)
    out = []
    for profile in rows:
        name = str(profile.get("name") or "").lower()
        sid = str(profile.get("student_id") or "").lower()
        cat = str((profile.get("prediction") or {}).get("category") or "").lower()
        if needle in name or needle in sid or needle in cat:
            out.append(profile)
    return out


def report_rows(profiles):
    rows = []
    for profile in profiles or []:
        pred = profile.get("prediction") or {}
        att = profile.get("attendance") or {}
        rows.append({
            "student_id": profile.get("student_id"),
            "name": profile.get("name"),
            "standing": pred.get("category"),
            "score": pred.get("score"),
            "attendance_rate": att.get("rate"),
            "consecutive_absences": att.get("consecutive_absences"),
        })
    return rows


def _norm_header(name):
    return str(name or "").strip().lower().replace(" ", "_")


def parse_import_csv(text, kind="academic"):
    raw = (text or "").lstrip("\ufeff").strip()
    if not raw:
        return [], "CSV is empty."
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return [], "CSV has no header row."
    kind = (kind or "academic").strip().lower()
    rows = []
    for i, item in enumerate(reader, start=2):
        mapped = {_norm_header(k): (v.strip() if isinstance(v, str) else v) for k, v in (item or {}).items()}
        sid = mapped.get("student_id") or mapped.get("id")
        try:
            student_id = int(sid)
        except (TypeError, ValueError):
            return [], f"Row {i}: student_id is required and must be a number."
        if kind in ("lms", "engagement"):
            event_type = mapped.get("event_type") or mapped.get("event") or mapped.get("type")
            if not event_type:
                return [], f"Row {i}: event_type is required."
            rows.append({
                "student_id": student_id,
                "event_type": event_type,
                "course_code": mapped.get("course_code") or mapped.get("course") or None,
            })
            continue
        assessment = mapped.get("assessment") or mapped.get("exam") or mapped.get("title") or "assessment"
        payload = {
            "student_id": student_id,
            "assessment": assessment,
            "semester": mapped.get("semester") or None,
        }
        for key, dest in (("score", "score"), ("max_score", "max_score"), ("gpa", "gpa")):
            if mapped.get(key) in (None, ""):
                continue
            try:
                payload[dest] = float(mapped[key])
            except (TypeError, ValueError):
                return [], f"Row {i}: {key} must be numeric."
        backlog = mapped.get("backlog")
        if backlog not in (None, ""):
            payload["backlog"] = str(backlog).strip().lower() in ("1", "true", "yes", "y")
        rows.append(payload)
    if not rows:
        return [], "CSV has a header but no data rows."
    return rows, ""


def settings_payload(raw):
    data = raw or {}
    if isinstance(data, str):
        import json
        try:
            data = json.loads(data)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "institution_name": str(data.get("institution_name") or data.get("name") or "").strip(),
        "support_note": str(data.get("support_note") or data.get("note") or "").strip(),
    }


def utc_now():
    return datetime.now(timezone.utc).isoformat()
