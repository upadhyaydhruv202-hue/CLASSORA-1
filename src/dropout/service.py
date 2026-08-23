"""Persistence, RBAC, audit, and analysis orchestration for dropout root-cause."""

from __future__ import annotations

import csv
import io
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone

from src.cohort.service import load_classroom_bundle
from src.dropout import engine
from src.dropout import stats as DS
from src.success import notify as notifier
from src.success import store

logger = logging.getLogger("classora.dropout")

# DEAN/DIRECTOR equivalent = administrator. HOD equivalent = teacher (scoped).
# Counsellor/faculty/mentor/student are denied this sensitive institutional view.
VIEW_ROLES = ("administrator", "teacher")
ANALYZE_ROLES = ("administrator", "teacher")
OUTCOME_ROLES = ("administrator",)
SETTINGS_ROLES = ("administrator",)
ANALYSIS_VERSION = engine.ANALYSIS_VERSION


def _now():
    return datetime.now(timezone.utc).isoformat()


def _jsonish(value, default=None):
    if value is None:
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    return default if default is not None else {}


def get_config():
    rows = store.select("institutional_dropout_settings") or []
    raw = _jsonish(rows[0].get("settings"), {}) if rows else {}
    return engine.normalize_config(raw)


def settings_record():
    rows = store.select("institutional_dropout_settings") or []
    if not rows:
        return {"settings": engine.normalize_config({}), "lastAnalysisAt": None, "lastAnalysis": None}
    row = rows[0]
    return {
        "settings": engine.normalize_config(_jsonish(row.get("settings"), {})),
        "lastAnalysisAt": row.get("last_analysis_at"),
        "lastAnalysis": _jsonish(row.get("last_analysis"), {}),
    }


def save_config(raw, actor=""):
    cfg = engine.normalize_config(raw)
    existing = store.select("institutional_dropout_settings") or []
    payload = {"settings": cfg, "updated_at": _now()}
    if existing:
        store.update("institutional_dropout_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        store.insert("institutional_dropout_settings", {"id": 1, **payload})
    logger.info("dropout_root settings updated actor=%s", actor or "unknown")
    return cfg


def audit(actor, action, resource="", detail=""):
    store.insert("audit_events", {
        "actor": actor or "",
        "action": action,
        "entity": resource,
        "detail": (detail or "")[:400],
    })


def _teacher_scope(session):
    if not session or session.get("user_role") != "teacher":
        return None
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    try:
        teacher_id = int(teacher_id)
    except (TypeError, ValueError):
        return {"teacher_id": None, "subject_ids": set(), "sections": set()}
    subject_ids = set()
    sections = set()
    try:
        from src.database.config import is_supabase_configured
        if is_supabase_configured():
            from src.database.db import get_teacher_subjects
            subjects = get_teacher_subjects(teacher_id) or []
        else:
            from src.database import local_store as local
            subjects = local.teacher_subjects(teacher_id) or []
        for row in subjects:
            if row.get("subject_id") is not None:
                subject_ids.add(int(row["subject_id"]))
            if row.get("section"):
                sections.add(str(row["section"]))
    except Exception:
        pass
    return {"teacher_id": teacher_id, "subject_ids": subject_ids, "sections": sections}


def _safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _filter_payload_for_teacher(payload, session):
    scope = _teacher_scope(session)
    if not scope:
        return payload
    data = dict(payload)
    cfg = get_config()
    slices = dict(data.get("slices") or {})
    sections = [
        row for row in (slices.get("sections") or [])
        if str(row.get("id")) in scope["sections"]
    ]
    courses = [
        row for row in (slices.get("courses") or [])
        if _safe_int(row.get("id")) in scope["subject_ids"]
    ]
    heatmap = [
        cell for cell in (data.get("heatmap") or [])
        if str(cell.get("section")) in scope["sections"]
    ]
    sem_acc = defaultdict(lambda: {"students": 0, "dropouts": 0})
    for cell in heatmap:
        if cell.get("suppressed"):
            continue
        sem_acc[str(cell.get("semester") or "unspecified")]["students"] += cell.get("students") or 0
        sem_acc[str(cell.get("semester") or "unspecified")]["dropouts"] += cell.get("dropouts") or 0
    semesters = []
    for sem, val in sem_acc.items():
        n, d = val["students"], val["dropouts"]
        suppressed = n < cfg["suppress_group_size"]
        semesters.append({
            "id": sem,
            "kind": "semester",
            "label": "Data suppressed due to small cohort size." if suppressed else f"Semester {sem}",
            "students": None if suppressed else n,
            "dropouts": None if suppressed else d,
            "dropoutRate": None if suppressed else DS.dropout_rate(d, n),
            "suppressed": suppressed,
            "volume": d,
            "rate": DS.dropout_rate(d, n) or 0,
        })
    semesters.sort(key=lambda row: (-(row.get("volume") or 0), -(row.get("rate") or 0)))
    enrolled = sum((row.get("students") or 0) for row in sections if not row.get("suppressed"))
    dropouts = sum((row.get("dropouts") or 0) for row in sections if not row.get("suppressed"))
    rate = DS.dropout_rate(dropouts, enrolled)
    overview = dict(data.get("overview") or {})
    overview["enrolled"] = enrolled
    overview["dropouts"] = dropouts
    overview["retained"] = max(0, enrolled - dropouts)
    overview["dropoutRate"] = rate
    overview["highestSection"] = next((row for row in sections if not row.get("suppressed")), None)
    overview["highestCourse"] = next((row for row in courses if not row.get("suppressed")), None)
    overview["highestSemester"] = next((row for row in semesters if not row.get("suppressed")), None)
    factors = [
        factor for factor in (data.get("factors") or [])
        if not str(factor.get("factorId") or "").startswith("COURSE_")
        or _safe_int(str(factor.get("factorId")).split("_")[-1]) in scope["subject_ids"]
    ]
    data["overview"] = overview
    data["slices"] = {"sections": sections, "semesters": semesters, "courses": courses}
    data["heatmap"] = heatmap
    data["factors"] = factors
    data["scope"] = "hod"
    data["scopeNote"] = (
        "Teacher access is limited to sections and courses you teach (HOD-equivalent scope). "
        "Institution-wide totals from unrelated sections are not shown."
    )
    data["story"] = f"{data['scopeNote']} {data.get('disclaimer') or engine.CAUSALITY_DISCLAIMER}"
    return data


def load_bundle():
    data = load_classroom_bundle()
    data["outcomes"] = store.select("student_academic_outcomes") or []
    return data


def record_outcome(student_id, status, *, period="", notes="", actor=""):
    wanted = str(status or "").strip().upper()
    if wanted not in engine.ALL_OUTCOME_STATUSES:
        return None, "Unknown outcome status."
    try:
        sid = int(student_id)
    except (TypeError, ValueError):
        return None, "student_id is required."
    if sid < 0:
        return None, "Demo student ids cannot be stored."
    row = {
        "student_id": sid,
        "status": wanted,
        "period": (period or "").strip() or None,
        "notes": (notes or "").strip()[:500] or None,
        "recorded_by": actor or "",
        "recorded_at": _now(),
    }
    saved = store.insert("student_academic_outcomes", row)
    if not saved:
        return None, "Could not save the academic outcome."
    audit(actor, "dropout_outcome_recorded", f"student_academic_outcomes:{sid}", wanted)
    return saved[0], ""


def import_outcomes(text, actor=""):
    raw = (text or "").lstrip("\ufeff").strip()
    if not raw:
        return [], "CSV is empty."
    reader = csv.DictReader(io.StringIO(raw))
    if not reader.fieldnames:
        return [], "CSV has no header row."
    saved = []
    for i, item in enumerate(reader, start=2):
        mapped = {str(k or "").strip().lower().replace(" ", "_"): (v.strip() if isinstance(v, str) else v) for k, v in (item or {}).items()}
        row, err = record_outcome(
            mapped.get("student_id") or mapped.get("id"),
            mapped.get("status") or mapped.get("outcome"),
            period=mapped.get("period") or "",
            notes=mapped.get("notes") or "",
            actor=actor,
        )
        if not row:
            return [], f"Row {i}: {err}"
        saved.append(row)
    return saved, ""


def list_outcomes():
    rows = store.select("student_academic_outcomes") or []
    return [{
        "id": row.get("id"),
        "studentId": row.get("student_id"),
        "status": row.get("status"),
        "period": row.get("period"),
        "recordedAt": row.get("recorded_at"),
        "recordedBy": row.get("recorded_by"),
    } for row in rows]


def persist_analysis(result, actor=""):
    identity = f"default|{ANALYSIS_VERSION}|current"
    existing = store.select("institutional_dropout_analyses", identity_key=identity) or []
    payload = {
        "institution_id": "default",
        "identity_key": identity,
        "analysis_version": ANALYSIS_VERSION,
        "period": "current",
        "insufficient": bool(result.get("insufficient")),
        "overview": result.get("overview") or {},
        "payload": result,
        "updated_at": _now(),
    }
    if existing:
        store.update("institutional_dropout_analyses", {"id": existing[0].get("id")}, payload)
        analysis_id = existing[0].get("id")
    else:
        payload["created_at"] = _now()
        saved = store.insert("institutional_dropout_analyses", payload)
        analysis_id = (saved or [{}])[0].get("id")
    store.delete("institutional_dropout_factors", analysis_id=analysis_id)
    store.delete("institutional_dropout_slices", analysis_id=analysis_id)
    store.delete("institutional_dropout_intersections", analysis_id=analysis_id)
    for factor in result.get("factors") or []:
        store.insert("institutional_dropout_factors", {
            "analysis_id": analysis_id,
            "factor_id": factor.get("factorId"),
            "payload": factor,
        })
    for kind, rows in (result.get("slices") or {}).items():
        for row in rows or []:
            store.insert("institutional_dropout_slices", {
                "analysis_id": analysis_id,
                "slice_kind": kind,
                "slice_id": row.get("id"),
                "payload": row,
            })
    for item in result.get("intersections") or []:
        store.insert("institutional_dropout_intersections", {
            "analysis_id": analysis_id,
            "combo": item.get("id"),
            "payload": item,
        })
    settings_rows = store.select("institutional_dropout_settings") or []
    summary = {
        "insufficient": bool(result.get("insufficient")),
        "enrolled": (result.get("overview") or {}).get("enrolled"),
        "dropouts": (result.get("overview") or {}).get("dropouts"),
        "dropoutRate": (result.get("overview") or {}).get("dropoutRate"),
        "factors": len(result.get("factors") or []),
        "actor": actor or "",
    }
    stamp = {"last_analysis_at": _now(), "last_analysis": summary, "updated_at": _now()}
    if settings_rows:
        store.update("institutional_dropout_settings", {"id": settings_rows[0].get("id", 1)}, stamp)
    else:
        store.insert("institutional_dropout_settings", {"id": 1, "settings": get_config(), **stamp})
    return {"analysisId": analysis_id, **summary}


def run_analysis(session=None, *, bundle=None, persist=True, actor=""):
    started = time.perf_counter()
    logger.info("dropout_root analysis started")
    try:
        cfg = get_config()
        data = bundle if bundle is not None else load_bundle()
        result = engine.analyze(data, cfg)
        summary = persist_analysis(result, actor=actor) if persist else {"analysisId": None}
        duration = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "dropout_root analysis completed duration_ms=%s dropouts=%s insufficient=%s",
            duration, (result.get("overview") or {}).get("dropouts"), result.get("insufficient"),
        )
        if persist and not result.get("insufficient"):
            emerging = [f for f in (result.get("factors") or []) if f.get("classification") == "EMERGING"]
            if emerging:
                top = emerging[0]
                notifier.notify(
                    role="administrator",
                    recipient_id="ops",
                    title="Emerging institutional dropout driver detected",
                    body=(
                        f"{top.get('factorName') or 'A factor'} increased in association with observed dropout outcomes. "
                        "Open Dropout Root Causes. This is an association, not a confirmed cause."
                    ),
                )
        result["persist"] = summary
        result["durationMs"] = duration
        if session and session.get("user_role") == "teacher":
            result = _filter_payload_for_teacher(result, session)
        return result
    except Exception:
        logger.exception("dropout_root analysis failed")
        raise


def latest_analysis(session=None):
    rows = store.select("institutional_dropout_analyses") or []
    if not rows:
        return None
    rows.sort(key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)
    payload = _jsonish(rows[0].get("payload"), {})
    if session and session.get("user_role") == "teacher":
        payload = _filter_payload_for_teacher(payload, session)
    payload["analysisId"] = rows[0].get("id")
    payload["updatedAt"] = rows[0].get("updated_at")
    return payload


def _unavailable_defaults():
    return {
        "FINANCIAL": {"available": False, "reason": engine.FINANCIAL_UNAVAILABLE, "status": "NOT_AVAILABLE"},
        "DEPARTMENT": {"available": False, "reason": engine.DEPARTMENT_UNAVAILABLE, "status": "NOT_AVAILABLE"},
        "INTERVENTION_IMPACT": {
            "available": False,
            "reason": (
                "Intervention impact tracking requires institutional intervention periods linked to dropout outcomes. "
                "Existing case-level intervention records are not used as institutional before/after evidence."
            ),
            "status": "NOT_AVAILABLE",
        },
    }


def overview(session):
    data = latest_analysis(session)
    settings = settings_record()
    unavailable = _unavailable_defaults()
    if data:
        unavailable.update(data.get("unavailable") or {})
    if not data:
        return {
            "available": True,
            "hasAnalysis": False,
            "insufficient": True,
            "reason": "No analysis has been run yet.",
            "emptyMessage": "No analysis has been run yet.",
            "lastAnalysisAt": settings.get("lastAnalysisAt"),
            "disclaimer": engine.CAUSALITY_DISCLAIMER,
            "unavailable": unavailable,
            "definition": {
                "dropoutStatuses": sorted(engine.DROPOUT_STATUSES),
                "retainedStatuses": sorted(engine.RETAINED_STATUSES),
            },
        }
    return {
        "available": True,
        "hasAnalysis": True,
        "insufficient": bool(data.get("insufficient")),
        "reason": data.get("reason"),
        "emptyMessage": data.get("emptyMessage") or data.get("reason"),
        "overview": data.get("overview"),
        "story": data.get("story"),
        "topFactors": (data.get("factors") or [])[:5],
        "firstYearShare": data.get("firstYearShare"),
        "noDominantFactor": data.get("noDominantFactor"),
        "disclaimer": data.get("disclaimer") or engine.CAUSALITY_DISCLAIMER,
        "unavailable": unavailable,
        "lastAnalysisAt": settings.get("lastAnalysisAt"),
        "updatedAt": data.get("updatedAt"),
        "version": data.get("version"),
        "definition": data.get("definition"),
        "scope": data.get("scope") or "institution",
        "scopeNote": data.get("scopeNote"),
        "dataQuality": data.get("dataQuality"),
    }


def summary(session):
    data = overview(session)
    ov = data.get("overview") or {}
    return {
        "available": True,
        "hasAnalysis": bool(data.get("hasAnalysis")),
        "insufficient": bool(data.get("insufficient")),
        "reason": data.get("reason"),
        "dropoutRate": ov.get("dropoutRate"),
        "dropouts": ov.get("dropouts"),
        "enrolled": ov.get("enrolled"),
        "changePp": ov.get("changePp"),
        "topFactor": ov.get("topFactor"),
        "lastAnalysisAt": data.get("lastAnalysisAt"),
        "disclaimer": data.get("disclaimer"),
        "scope": data.get("scope") or "institution",
    }


def get_section(session, key, default=None):
    data = latest_analysis(session)
    if not data:
        return default
    return data.get(key, default)


def filtered_factors(session, factor="", classification="", confidence=""):
    rows = list(get_section(session, "factors", []) or [])
    out = []
    for item in rows:
        if factor:
            needle = factor.lower()
            if needle not in str(item.get("factorId") or "").lower() and needle not in str(item.get("factorName") or "").lower():
                continue
        if classification and str(item.get("classification") or "").upper() != classification.upper():
            continue
        if confidence and str(item.get("confidence") or "").upper() != confidence.upper():
            continue
        out.append(item)
    return out


def factor_detail(session, factor_id):
    data = latest_analysis(session)
    if not data:
        return None, "No analysis has been run yet."
    for factor in data.get("factors") or []:
        if str(factor.get("factorId")) == str(factor_id):
            return factor, ""
    return None, "Factor not found in the current analysis."


def slice_detail(session, kind, item_id):
    data = latest_analysis(session)
    if not data:
        return None, "No analysis has been run yet."
    mapping = {"section": "sections", "department": "sections", "semester": "semesters", "course": "courses"}
    bucket = mapping.get((kind or "").lower())
    if not bucket:
        return None, "Unknown slice kind."
    rows = (data.get("slices") or {}).get(bucket) or []
    for row in rows:
        if str(row.get("id")) == str(item_id):
            if row.get("suppressed"):
                return {"suppressed": True, "label": "Data suppressed due to small cohort size."}, ""
            return row, ""
    return None, "Slice not found in the current analysis."


def compare(session, kind, left_id, right_id):
    data = latest_analysis(session)
    if not data:
        return None, "No analysis has been run yet."
    kind = (kind or "").lower()
    if kind in ("year", "period"):
        rows = data.get("trends") or []
        key = "period"
    else:
        mapping = {"section": "sections", "department": "sections", "semester": "semesters", "course": "courses"}
        bucket = mapping.get(kind)
        if not bucket:
            return None, "Comparison kind must be section, semester, course, or period."
        rows = (data.get("slices") or {}).get(bucket) or []
        key = "id"
    left = next((row for row in rows if str(row.get(key)) == str(left_id)), None)
    right = next((row for row in rows if str(row.get(key)) == str(right_id)), None)
    if not left or not right:
        return None, "Both comparison groups must exist in the current analysis."
    if left.get("suppressed") or right.get("suppressed"):
        return None, "Data suppressed due to small cohort size."
    return {
        "kind": kind,
        "left": left,
        "right": right,
        "rateDifference": DS.risk_difference(left.get("dropoutRate"), right.get("dropoutRate")),
        "relativeRisk": DS.relative_risk(left.get("dropoutRate"), right.get("dropoutRate")),
        "note": "Comparison of observed dropout rates. This is an association view, not a causal finding.",
    }, ""


def report_payload(session):
    data = latest_analysis(session)
    if not data:
        return None
    return {
        "analysisPeriod": "current",
        "version": data.get("version"),
        "overview": data.get("overview"),
        "story": data.get("story"),
        "factors": data.get("factors") or [],
        "slices": data.get("slices") or {},
        "recommendations": data.get("recommendations") or [],
        "methodology": {
            "definition": data.get("definition"),
            "disclaimer": data.get("disclaimer"),
            "dataQuality": data.get("dataQuality"),
            "unavailable": data.get("unavailable"),
        },
        "limitations": [
            engine.CAUSALITY_DISCLAIMER,
            engine.FINANCIAL_UNAVAILABLE,
            engine.DEPARTMENT_UNAVAILABLE,
        ],
    }


def report_rows(session):
    data = latest_analysis(session) or {}
    rows = []
    overview_row = data.get("overview") or {}
    rows.append({
        "section": "overview",
        "label": "Institution" if data.get("scope") != "hod" else "Authorized scope",
        "students": overview_row.get("enrolled"),
        "dropouts": overview_row.get("dropouts"),
        "dropoutRate": overview_row.get("dropoutRate"),
        "note": data.get("disclaimer"),
    })
    for factor in data.get("factors") or []:
        rows.append({
            "section": "factor",
            "label": factor.get("factorName"),
            "students": factor.get("affectedStudents"),
            "dropouts": factor.get("affectedDropouts"),
            "dropoutRate": factor.get("dropoutRate"),
            "relativeRisk": factor.get("relativeRisk"),
            "riskDifference": factor.get("riskDifference"),
            "confidence": factor.get("confidence"),
            "note": factor.get("evidence"),
        })
    return rows


def csv_text(session):
    rows = report_rows(session)
    if not rows:
        return ""
    keys = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=keys, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()
