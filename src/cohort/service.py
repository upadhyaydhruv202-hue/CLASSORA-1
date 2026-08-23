"""Persistence, RBAC-aware reads, and analysis orchestration for cohort anomalies."""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from src.cohort import engine
from src.cohort import stats as S
from src.success import notify as notifier
from src.success import store

logger = logging.getLogger("classora.cohort")

OPEN_STATUSES = ("NEW", "INVESTIGATING", "ACKNOWLEDGED")
ALL_STATUSES = OPEN_STATUSES + ("RESOLVED", "DISMISSED")
VIEW_ROLES = ("administrator", "teacher", "counsellor")
ANALYZE_ROLES = ("administrator", "teacher")
MANAGE_ROLES = ("administrator", "teacher")
SETTINGS_ROLES = ("administrator",)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _num(value):
    return S.finite(value)


def _jsonish(value, default=None):
    if value is None:
        return default if default is not None else {}
    if isinstance(value, (dict, list)):
        return value
    return default if default is not None else {}


def get_config():
    rows = store.select("institutional_anomaly_settings") or []
    raw = {}
    if rows:
        raw = _jsonish(rows[0].get("settings"), {})
    return engine.normalize_config(raw)


def settings_record():
    rows = store.select("institutional_anomaly_settings") or []
    if not rows:
        return {
            "settings": engine.normalize_config({}),
            "lastAnalysisAt": None,
            "lastAnalysis": None,
        }
    row = rows[0]
    return {
        "settings": engine.normalize_config(_jsonish(row.get("settings"), {})),
        "lastAnalysisAt": row.get("last_analysis_at"),
        "lastAnalysis": _jsonish(row.get("last_analysis"), {}),
    }


def save_config(raw, actor=""):
    cfg = engine.normalize_config(raw)
    existing = store.select("institutional_anomaly_settings") or []
    payload = {"settings": cfg, "updated_at": _now()}
    if existing:
        store.update("institutional_anomaly_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        payload["id"] = 1
        store.insert("institutional_anomaly_settings", payload)
    logger.info("cohort_anomaly settings updated actor=%s", actor or "unknown")
    return cfg


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
            sid = row.get("subject_id")
            if sid is not None:
                subject_ids.add(int(sid))
            if row.get("section"):
                sections.add(str(row.get("section")))
    except Exception:
        pass
    return {"teacher_id": teacher_id, "subject_ids": subject_ids, "sections": sections}


def _visible_event(row, session):
    role = (session or {}).get("user_role")
    if role in ("administrator", "counsellor"):
        return True
    if role != "teacher":
        return False
    scope = _teacher_scope(session)
    if not scope:
        return False
    if row.get("cohort_type") == engine.COHORT_INSTITUTION:
        return True
    if row.get("teacher_id") is not None and _num(row.get("teacher_id")) == scope["teacher_id"]:
        return True
    if row.get("subject_id") is not None and int(row.get("subject_id")) in scope["subject_ids"]:
        return True
    if row.get("section") and str(row.get("section")) in scope["sections"]:
        return True
    meta = _jsonish(row.get("metadata"), {})
    for child in meta.get("hierarchy") or []:
        if child.get("cohortType") == engine.COHORT_COURSE and child.get("label"):
            return True
    return False


def load_classroom_bundle():
    from src.database.config import is_supabase_configured, supabase
    from src.database.db import get_all_students

    institution_name = ""
    try:
        rows = store.select("institution_settings") or []
        if rows:
            settings = rows[0].get("settings") or {}
            if isinstance(settings, dict):
                institution_name = str(settings.get("institution_name") or "").strip()
    except Exception:
        institution_name = ""

    moderation = []
    try:
        if store.available("student_moderation_status"):
            moderation = store.select("student_moderation_status") or []
    except Exception:
        moderation = []

    academic = store.select("academic_records") or []
    lms = store.select("lms_events") or []

    if not is_supabase_configured():
        from src.database import local_store as local
        data = local.read_db()
        return {
            "students": [{"student_id": r.get("student_id"), "name": r.get("name")} for r in data.get("students") or []],
            "subjects": data.get("subjects") or [],
            "enrollments": data.get("subject_students") or [],
            "attendance": data.get("attendance_logs") or [],
            "academic": academic,
            "lms": lms,
            "moderation": moderation,
            "institution_name": institution_name,
        }

    def _all(table, columns):
        rows = []
        start = 0
        page = 1000
        while True:
            batch = supabase.table(table).select(columns).range(start, start + page - 1).execute().data or []
            rows.extend(batch)
            if len(batch) < page:
                break
            start += page
        return rows

    students = get_all_students("student_id, name") or []
    try:
        subjects = _all("subjects", "subject_id, name, section, subject_code, teacher_id")
    except Exception:
        subjects = []
    try:
        enrollments = _all("subject_students", "student_id, subject_id")
    except Exception:
        enrollments = []
    try:
        attendance = _all("attendance_logs", "student_id, subject_id, timestamp, is_present")
    except Exception:
        attendance = []
    return {
        "students": students,
        "subjects": subjects,
        "enrollments": enrollments,
        "attendance": attendance,
        "academic": academic,
        "lms": lms,
        "moderation": moderation,
        "institution_name": institution_name,
    }


def _event_key(identity_key, window_end):
    day = str(window_end or "")[:10]
    return f"{identity_key}|{day}"


def _persist_snapshots(snapshots):
    existing = store.select("institutional_anomaly_snapshots") or []
    index = {}
    for row in existing:
        key = (row.get("cohort_key"), row.get("metric_name"), str(row.get("period_start") or ""), row.get("period_kind"))
        index[key] = row
    written = 0
    for row in snapshots or []:
        key = (row.get("cohort_key"), row.get("metric_name"), str(row.get("period_start") or ""), row.get("period_kind"))
        payload = {
            "cohort_key": row.get("cohort_key"),
            "metric_name": row.get("metric_name"),
            "period_start": row.get("period_start"),
            "period_end": row.get("period_end"),
            "period_kind": row.get("period_kind") or "WEEK",
            "value": row.get("value"),
            "record_count": row.get("record_count"),
            "expected_count": row.get("expected_count"),
            "cohort_size": row.get("cohort_size"),
        }
        prior = index.get(key)
        if prior:
            store.update("institutional_anomaly_snapshots", {"id": prior.get("id")}, payload)
        else:
            store.insert("institutional_anomaly_snapshots", payload)
        written += 1
    return written


def _replace_metrics(anomaly_id, members):
    store.delete("institutional_anomaly_metrics", anomaly_id=anomaly_id)
    rows = []
    for item in members or []:
        saved = store.insert("institutional_anomaly_metrics", {
            "anomaly_id": anomaly_id,
            "metric_name": item.get("metric_name"),
            "baseline": item.get("baseline"),
            "current_value": item.get("current"),
            "deviation": item.get("pp_change"),
            "z_score": item.get("z"),
            "robust_z": item.get("robust_z"),
            "change_percentage": item.get("rel_change"),
            "confidence": item.get("confidence"),
        })
        if saved:
            rows.extend(saved)
    return rows


def _row_payload(event, *, event_key, existing=None):
    members = event.get("members") or []
    lead = members[0] if members else {}
    meta = {
        "hierarchy": event.get("children") or [],
        "comparisons": event.get("comparisons") or {},
        "isPrimary": True,
        "affectedStudentIds": event.get("affected_ids") or [],
        "metrics": [
            {
                "name": m.get("metric_name"),
                "label": engine._metric_label(m.get("metric_name")),
                "current": m.get("current"),
                "baseline": m.get("baseline"),
                "ppChange": m.get("pp_change"),
                "relChange": m.get("rel_change"),
                "zScore": m.get("z"),
                "robustZ": m.get("robust_z"),
                "confidence": m.get("confidence"),
                "recordCount": m.get("record_count"),
                "expectedCount": m.get("expected_count"),
            }
            for m in members
        ],
        "disclaimer": event.get("disclaimer") or engine.HYPOTHESIS_DISCLAIMER,
        "persistencePeriods": int(((existing or {}).get("metadata") or {}).get("persistencePeriods") or 0) + (1 if existing else 0),
        "recoveryStreak": 0,
        "notified": bool(((existing or {}).get("metadata") or {}).get("notified")),
    }
    now = _now()
    return {
        "institution_id": "default",
        "event_key": event_key,
        "identity_key": event.get("identity_key"),
        "parent_id": None,
        "cohort_type": event.get("cohort_type"),
        "cohort_key": event.get("cohort_key"),
        "cohort_label": event.get("cohort_label"),
        "section": event.get("section"),
        "subject_id": event.get("subject_id"),
        "subject_name": event.get("subject_name"),
        "subject_code": event.get("subject_code"),
        "teacher_id": event.get("teacher_id"),
        "semester": event.get("semester"),
        "metric_type": event.get("metric_type"),
        "anomaly_score": event.get("score") or 0,
        "severity": event.get("severity") or "WATCH",
        "confidence": event.get("confidence"),
        "baseline_value": event.get("baseline") if event.get("baseline") is not None else lead.get("baseline"),
        "current_value": event.get("current") if event.get("current") is not None else lead.get("current"),
        "absolute_change": event.get("pp_change") if event.get("pp_change") is not None else lead.get("pp_change"),
        "percentage_change": event.get("rel_change") if event.get("rel_change") is not None else lead.get("rel_change"),
        "z_score": event.get("z"),
        "robust_z_score": event.get("robust_z"),
        "cohort_size": event.get("cohort_size") or 0,
        "affected_student_count": event.get("affected_count") or 0,
        "affected_percentage": event.get("affected_pct") or 0,
        "window_start": event.get("window_start"),
        "window_end": event.get("window_end"),
        "baseline_start": event.get("baseline_start"),
        "baseline_end": event.get("baseline_end"),
        "last_observed_at": now,
        "explanation": event.get("explanation"),
        "possible_causes": event.get("possible_causes") or [],
        "data_quality": {
            "collapsed": bool(event.get("collapsed")),
            "recordCount": event.get("record_count"),
            "expectedCount": event.get("expected_count"),
        },
        "metadata": meta,
        "updated_at": now,
    }


def _maybe_notify(row, created):
    if not created:
        return
    meta = _jsonish(row.get("metadata"), {})
    if meta.get("notified"):
        return
    cfg = get_config()
    severity = str(row.get("severity") or "").upper()
    allowed = {str(x).upper() for x in cfg.get("notify_severities") or []}
    if severity not in allowed:
        return
    title = f"{severity.title()}-severity cohort anomaly detected"
    body = (
        f"{row.get('cohort_label') or 'A cohort'} {str(row.get('metric_type') or '').replace('_', ' ').lower()} "
        f"changed {row.get('absolute_change')} points, affecting {row.get('affected_student_count')} of "
        f"{row.get('cohort_size')} students. Open Institutional Anomalies."
    )
    notifier.notify(role="administrator", recipient_id="ops", title=title, body=body)
    meta["notified"] = True
    store.update("institutional_anomalies", {"id": row.get("id")}, {"metadata": meta})


def persist_analysis(result, actor=""):
    cfg = result.get("config") or get_config()
    snap_count = _persist_snapshots(result.get("snapshots") or [])
    existing = store.select("institutional_anomalies") or []
    open_rows = [row for row in existing if str(row.get("status") or "NEW").upper() in OPEN_STATUSES]
    by_identity = {row.get("identity_key"): row for row in open_rows}
    detected = {}
    created = 0
    updated = 0
    for event in result.get("events") or []:
        identity = event.get("identity_key")
        prior = by_identity.get(identity)
        event_key = prior.get("event_key") if prior else _event_key(identity, event.get("window_end"))
        payload = _row_payload(event, event_key=event_key, existing=prior)
        if prior:
            if str(prior.get("status") or "").upper() != "DISMISSED":
                store.update("institutional_anomalies", {"id": prior.get("id")}, payload)
                payload["id"] = prior.get("id")
                payload["status"] = prior.get("status") or "NEW"
                payload["first_detected_at"] = prior.get("first_detected_at")
                _replace_metrics(prior.get("id"), event.get("members") or [])
                updated += 1
                detected[identity] = {**prior, **payload}
        else:
            payload["status"] = "NEW"
            payload["first_detected_at"] = _now()
            saved = store.insert("institutional_anomalies", payload)
            if saved:
                row = saved[0]
                _replace_metrics(row.get("id"), event.get("members") or [])
                created += 1
                detected[identity] = row
                _maybe_notify(row, True)

    resolved = 0
    for row in open_rows:
        identity = row.get("identity_key")
        if identity in detected:
            continue
        meta = _jsonish(row.get("metadata"), {})
        streak = int(meta.get("recoveryStreak") or 0) + 1
        meta["recoveryStreak"] = streak
        values = {"metadata": meta, "updated_at": _now()}
        if streak >= int(cfg.get("recovery_periods") or 2) and str(row.get("status") or "").upper() != "DISMISSED":
            values["status"] = "RESOLVED"
            resolved += 1
        store.update("institutional_anomalies", {"id": row.get("id")}, values)

    summary = {
        "created": created,
        "updated": updated,
        "resolved": resolved,
        "snapshots": snap_count,
        "events": len(result.get("events") or []),
        "cohortsAnalyzed": result.get("cohorts_analyzed") or 0,
        "coldStart": bool(result.get("cold_start")),
        "actor": actor or "",
        "asOf": result.get("as_of"),
    }
    settings_rows = store.select("institutional_anomaly_settings") or []
    analysis_payload = {
        "last_analysis_at": _now(),
        "last_analysis": summary,
        "updated_at": _now(),
    }
    if settings_rows:
        store.update("institutional_anomaly_settings", {"id": settings_rows[0].get("id", 1)}, analysis_payload)
    else:
        store.insert("institutional_anomaly_settings", {
            "id": 1,
            "settings": cfg,
            **analysis_payload,
        })
    return summary


def run_analysis(session=None, *, bundle=None, as_of=None, persist=True, actor=""):
    started = time.perf_counter()
    logger.info("cohort_anomaly analysis started")
    try:
        cfg = get_config()
        data = bundle if bundle is not None else load_classroom_bundle()
        result = engine.analyze(data, cfg, as_of=as_of)
        summary = persist_analysis(result, actor=actor) if persist else {
            "created": 0,
            "updated": 0,
            "resolved": 0,
            "snapshots": 0,
            "events": len(result.get("events") or []),
            "cohortsAnalyzed": result.get("cohorts_analyzed") or 0,
            "coldStart": bool(result.get("cold_start")),
        }
        duration = round((time.perf_counter() - started) * 1000, 1)
        logger.info(
            "cohort_anomaly analysis completed duration_ms=%s cohorts=%s anomalies=%s",
            duration,
            summary.get("cohortsAnalyzed"),
            summary.get("events"),
        )
        result["persist"] = summary
        result["durationMs"] = duration
        return result
    except Exception:
        logger.exception("cohort_anomaly analysis failed")
        raise


def _public_event(row, session=None, *, include_students=False):
    if not row:
        return None
    meta = _jsonish(row.get("metadata"), {})
    causes = row.get("possible_causes") or []
    if isinstance(causes, str):
        causes = []
    role = (session or {}).get("user_role")
    show_ids = bool(include_students and role == "administrator")
    return {
        "id": row.get("id"),
        "eventKey": row.get("event_key"),
        "identityKey": row.get("identity_key"),
        "cohortType": row.get("cohort_type"),
        "cohortKey": row.get("cohort_key"),
        "cohortLabel": row.get("cohort_label"),
        "section": row.get("section"),
        "subjectId": row.get("subject_id"),
        "subjectName": row.get("subject_name"),
        "subjectCode": row.get("subject_code"),
        "semester": row.get("semester"),
        "metricType": row.get("metric_type"),
        "anomalyScore": _num(row.get("anomaly_score")),
        "severity": row.get("severity"),
        "confidence": _num(row.get("confidence")),
        "baselineValue": _num(row.get("baseline_value")),
        "currentValue": _num(row.get("current_value")),
        "absoluteChange": _num(row.get("absolute_change")),
        "percentageChange": _num(row.get("percentage_change")),
        "zScore": _num(row.get("z_score")),
        "robustZScore": _num(row.get("robust_z_score")),
        "cohortSize": row.get("cohort_size") or 0,
        "affectedStudentCount": row.get("affected_student_count") or 0,
        "affectedPercentage": _num(row.get("affected_percentage")),
        "windowStart": row.get("window_start"),
        "windowEnd": row.get("window_end"),
        "baselineStart": row.get("baseline_start"),
        "baselineEnd": row.get("baseline_end"),
        "detectedAt": row.get("first_detected_at") or row.get("created_at"),
        "lastObservedAt": row.get("last_observed_at"),
        "status": row.get("status") or "NEW",
        "explanation": row.get("explanation") or "",
        "possibleCauses": causes,
        "dataQuality": _jsonish(row.get("data_quality"), {}),
        "hierarchy": meta.get("hierarchy") or [],
        "comparisons": meta.get("comparisons") or {},
        "metrics": meta.get("metrics") or [],
        "disclaimer": meta.get("disclaimer") or engine.HYPOTHESIS_DISCLAIMER,
        "affectedStudentIds": meta.get("affectedStudentIds") if show_ids else [],
        "hasFacultyPattern": any(
            str((c or {}).get("id")) == "faculty_course" for c in (causes if isinstance(causes, list) else [])
        ),
    }


def _matches_filters(row, filters):
    filters = filters or {}
    if filters.get("severity") and str(row.get("severity") or "").upper() != str(filters["severity"]).upper():
        return False
    if filters.get("status") and str(row.get("status") or "").upper() != str(filters["status"]).upper():
        return False
    if filters.get("metric") and str(row.get("metric_type") or "").upper() != str(filters["metric"]).upper():
        return False
    if filters.get("section") and str(row.get("section") or "") != str(filters["section"]):
        return False
    if filters.get("semester") and str(row.get("semester") or "") != str(filters["semester"]):
        return False
    if filters.get("course"):
        needle = str(filters["course"]).strip().lower()
        hay = " ".join([
            str(row.get("subject_name") or ""),
            str(row.get("subject_code") or ""),
            str(row.get("subject_id") or ""),
        ]).lower()
        if needle not in hay:
            return False
    if filters.get("cohort_type") and str(row.get("cohort_type") or "").upper() != str(filters["cohort_type"]).upper():
        return False
    start = filters.get("start")
    end = filters.get("end")
    detected = str(row.get("first_detected_at") or row.get("created_at") or "")
    if start and detected[:10] < str(start)[:10]:
        return False
    if end and detected[:10] > str(end)[:10]:
        return False
    q = str(filters.get("search") or "").strip().lower()
    if q:
        blob = " ".join([
            str(row.get("cohort_label") or ""),
            str(row.get("subject_name") or ""),
            str(row.get("subject_code") or ""),
            str(row.get("section") or ""),
            str(row.get("semester") or ""),
            str(row.get("explanation") or ""),
            str(row.get("metric_type") or ""),
        ]).lower()
        if q not in blob:
            return False
    return True


def list_events(session, filters=None):
    filters = filters or {}
    rows = [row for row in (store.select("institutional_anomalies") or []) if _visible_event(row, session)]
    rows = [row for row in rows if row.get("parent_id") in (None, "")]
    rows = [row for row in rows if _matches_filters(row, filters)]
    sort = str(filters.get("sort") or "newest").lower()
    def key(row):
        if sort == "severity":
            order = {"CRITICAL": 4, "HIGH": 3, "MODERATE": 2, "WATCH": 1}
            return (-order.get(str(row.get("severity") or "").upper(), 0), -S.finite(row.get("anomaly_score"), 0))
        if sort in ("score", "anomaly_score"):
            return -S.finite(row.get("anomaly_score"), 0)
        if sort in ("affected", "affected_students"):
            return -(row.get("affected_student_count") or 0)
        if sort in ("affected_pct", "affected_percentage"):
            return -S.finite(row.get("affected_percentage"), 0)
        return str(row.get("first_detected_at") or row.get("created_at") or "")
    reverse = sort != "oldest"
    rows.sort(key=key, reverse=reverse)
    return [_public_event(row, session) for row in rows]


def get_event(event_id, session, *, include_students=False):
    rows = store.select("institutional_anomalies", id=_coerce_id(event_id)) or []
    if not rows:
        try:
            rows = [row for row in (store.select("institutional_anomalies") or []) if str(row.get("id")) == str(event_id)]
        except Exception:
            rows = []
    if not rows:
        return None, "Anomaly not found."
    row = rows[0]
    if not _visible_event(row, session):
        return None, "Anomaly not found."
    return _public_event(row, session, include_students=include_students), ""


def _coerce_id(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _get_raw(event_id, session):
    rows = store.select("institutional_anomalies", id=_coerce_id(event_id)) or []
    if not rows:
        rows = [row for row in (store.select("institutional_anomalies") or []) if str(row.get("id")) == str(event_id)]
    if not rows:
        return None
    row = rows[0]
    if not _visible_event(row, session):
        return None
    return row


def timeline(event_id, session):
    row = _get_raw(event_id, session)
    if not row:
        return None, "Anomaly not found."
    snaps = store.select("institutional_anomaly_snapshots", cohort_key=row.get("cohort_key")) or []
    members = _jsonish(row.get("metadata"), {}).get("metrics") or []
    names = [m.get("name") for m in members if m.get("name")]
    if row.get("metric_type") == engine.METRIC_ATTENDANCE:
        names = names or ["attendance_rate"]
    series = defaultdict_series(snaps, names)
    return {
        "anomalyId": row.get("id"),
        "cohortKey": row.get("cohort_key"),
        "windowStart": row.get("window_start"),
        "windowEnd": row.get("window_end"),
        "series": series,
    }, ""


def defaultdict_series(snaps, names):
    from collections import defaultdict
    grouped = defaultdict(list)
    for row in snaps or []:
        name = row.get("metric_name")
        if names and name not in names:
            continue
        grouped[name].append({
            "start": row.get("period_start"),
            "end": row.get("period_end"),
            "kind": row.get("period_kind"),
            "value": _num(row.get("value")),
            "recordCount": row.get("record_count"),
            "label": engine._metric_label(name),
        })
    for key in grouped:
        grouped[key].sort(key=lambda item: str(item.get("start") or ""))
    if not grouped and names:
        for name in names:
            grouped[name] = []
    return dict(grouped)


def evidence(event_id, session):
    public, msg = get_event(event_id, session)
    if not public:
        return None, msg
    return {
        "anomaly": public,
        "explanation": public.get("explanation"),
        "possibleCauses": public.get("possibleCauses"),
        "metrics": public.get("metrics"),
        "dataQuality": public.get("dataQuality"),
        "disclaimer": public.get("disclaimer"),
    }, ""


def cohort_view(event_id, session):
    row = _get_raw(event_id, session)
    if not row:
        return None, "Anomaly not found."
    public, _msg = get_event(event_id, session, include_students=session.get("user_role") == "administrator")
    payload = {
        "anomaly": public,
        "cohortSize": row.get("cohort_size"),
        "affectedStudentCount": row.get("affected_student_count"),
        "affectedPercentage": row.get("affected_percentage"),
        "display": f"{row.get('affected_student_count') or 0} of {row.get('cohort_size') or 0} students affected ({row.get('affected_percentage') or 0}%)",
        "studentIdentitiesHidden": session.get("user_role") != "administrator",
    }
    if session.get("user_role") == "administrator":
        payload["affectedStudentIds"] = _jsonish(row.get("metadata"), {}).get("affectedStudentIds") or []
    return payload, ""


def add_note(event_id, session, note, actor=""):
    row = _get_raw(event_id, session)
    if not row:
        return None, "Anomaly not found."
    text = str(note or "").strip()
    if len(text) < 3:
        return None, "Note must be at least 3 characters."
    saved = store.insert("institutional_anomaly_notes", {
        "anomaly_id": row.get("id"),
        "actor": actor or "",
        "note": text[:2000],
        "created_at": _now(),
    })
    if not saved:
        return None, "Could not save the note."
    return saved[0], ""


def list_notes(event_id, session):
    row = _get_raw(event_id, session)
    if not row:
        return [], "Anomaly not found."
    rows = store.select("institutional_anomaly_notes", anomaly_id=row.get("id")) or []
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return rows, ""


def set_status(event_id, session, status, actor=""):
    row = _get_raw(event_id, session)
    if not row:
        return None, "Anomaly not found."
    wanted = str(status or "").strip().upper()
    allowed = {
        "ACKNOWLEDGE": "ACKNOWLEDGED",
        "ACKNOWLEDGED": "ACKNOWLEDGED",
        "INVESTIGATE": "INVESTIGATING",
        "INVESTIGATING": "INVESTIGATING",
        "RESOLVE": "RESOLVED",
        "RESOLVED": "RESOLVED",
        "DISMISS": "DISMISSED",
        "DISMISSED": "DISMISSED",
    }
    next_status = allowed.get(wanted)
    if not next_status:
        return None, "Unknown status."
    updated = store.update("institutional_anomalies", {"id": row.get("id")}, {
        "status": next_status,
        "updated_at": _now(),
    })
    if not updated:
        return None, "Could not update the anomaly."
    store.insert("audit_events", {
        "actor": actor or "",
        "action": f"anomaly_{next_status.lower()}",
        "entity": f"institutional_anomalies:{row.get('id')}",
        "detail": f"status={next_status}",
    })
    return _public_event(updated[0], session), ""


def summary(session):
    settings = settings_record()
    rows = [row for row in (store.select("institutional_anomalies") or []) if _visible_event(row, session)]
    rows = [row for row in rows if row.get("parent_id") in (None, "")]
    active = [row for row in rows if str(row.get("status") or "NEW").upper() in OPEN_STATUSES]
    resolved = [row for row in rows if str(row.get("status") or "").upper() == "RESOLVED"]
    counts = {"CRITICAL": 0, "HIGH": 0, "MODERATE": 0, "WATCH": 0}
    affected_students = 0
    cohorts = set()
    top = None
    for row in active:
        sev = str(row.get("severity") or "").upper()
        if sev in counts:
            counts[sev] += 1
        affected_students += int(row.get("affected_student_count") or 0)
        if row.get("cohort_key"):
            cohorts.add(row.get("cohort_key"))
        if top is None or S.finite(row.get("anomaly_score"), 0) > S.finite(top.get("anomaly_score"), 0):
            top = row
    return {
        "available": True,
        "active": len(active),
        "critical": counts["CRITICAL"],
        "high": counts["HIGH"],
        "moderate": counts["MODERATE"],
        "watch": counts["WATCH"],
        "resolved": len(resolved),
        "cohortsAffected": len(cohorts),
        "studentsAffected": affected_students,
        "mostAffected": _public_event(top, session) if top else None,
        "lastAnalysisAt": settings.get("lastAnalysisAt"),
        "lastAnalysis": settings.get("lastAnalysis"),
        "coldStart": bool((settings.get("lastAnalysis") or {}).get("coldStart")),
        "dimensions": {
            "department": False,
            "year": False,
            "section": True,
            "course": True,
            "semester": True,
            "calendar": False,
        },
        "disclaimer": engine.HYPOTHESIS_DISCLAIMER,
    }
