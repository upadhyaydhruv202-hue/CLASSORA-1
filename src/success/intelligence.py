"""Assemble Student Success intelligence from existing attendance APIs + optional new tables."""

from collections import defaultdict
from datetime import datetime

from src.database.config import is_supabase_configured, supabase
from src.database.db import get_all_students, get_student_attendance, get_student_subjects
from src.success import store
from src.success.risk_model import (
    DEFAULT_LIBRARY,
    academic_features,
    attendance_features,
    engagement_features,
    prioritize,
    recommend,
    score_student,
    temporal_features,
)


def audit(actor, action, entity="", detail=""):
    store.insert("audit_events", {"actor": actor, "action": action, "entity": entity, "detail": detail})


def _real_bundle(teacher_id=None):
    if not is_supabase_configured():
        from src.database import local_store as local
        data = local.read_db()
        students = [local.public_student(row) for row in data.get("students") or []]
        subjects = {int(s["subject_id"]): s for s in data.get("subjects") or []}
        enrollments = []
        for row in data.get("subject_students") or []:
            sub = subjects.get(int(row.get("subject_id") or 0)) or {}
            enrollments.append({
                "student_id": row.get("student_id"),
                "subject_id": row.get("subject_id"),
                "subjects": {
                    "name": sub.get("name"),
                    "section": sub.get("section"),
                    "subject_code": sub.get("subject_code"),
                    "teacher_id": sub.get("teacher_id"),
                },
            })
        logs = []
        for row in data.get("attendance_logs") or []:
            sub = subjects.get(int(row.get("subject_id") or 0)) or {}
            item = dict(row)
            item["subjects"] = {
                "name": sub.get("name"),
                "section": sub.get("section"),
                "subject_code": sub.get("subject_code"),
                "teacher_id": sub.get("teacher_id"),
            }
            logs.append(item)
        if teacher_id is not None:
            teacher_id = int(teacher_id)
            allowed = {e["student_id"] for e in enrollments if (e.get("subjects") or {}).get("teacher_id") == teacher_id}
            students = [s for s in students if s.get("student_id") in allowed]
            enrollments = [e for e in enrollments if (e.get("subjects") or {}).get("teacher_id") == teacher_id]
            logs = [r for r in logs if (r.get("subjects") or {}).get("teacher_id") == teacher_id]
        return {
            "students": students,
            "enrollments": enrollments,
            "logs": logs,
            "academic": store.select("academic_records"),
            "lms": store.select("lms_events"),
            "cases": store.select("intervention_cases"),
            "recommendations": store.select("intervention_recommendations"),
            "demo": False,
        }

    students = get_all_students() or []
    enrollments = []
    logs = []
    if is_supabase_configured():
        try:
            enrollments = supabase.table("subject_students").select(
                "student_id, subject_id, subjects(name, section, subject_code, teacher_id)"
            ).execute().data or []
        except Exception:
            enrollments = []
        try:
            q = supabase.table("attendance_logs").select("*, subjects(name, section, subject_code, teacher_id)")
            if teacher_id:
                q = q.eq("subjects.teacher_id", teacher_id)
            logs = q.execute().data or []
        except Exception:
            logs = []
    if teacher_id:
        allowed = {e["student_id"] for e in enrollments if (e.get("subjects") or {}).get("teacher_id") == teacher_id}
        students = [s for s in students if s.get("student_id") in allowed]
        enrollments = [e for e in enrollments if (e.get("subjects") or {}).get("teacher_id") == teacher_id]
        logs = [r for r in logs if (r.get("subjects") or {}).get("teacher_id") == teacher_id]
    academic = store.select("academic_records")
    lms = store.select("lms_events")
    cases = store.select("intervention_cases")
    recs = store.select("intervention_recommendations")
    return {
        "students": students,
        "enrollments": enrollments,
        "logs": logs,
        "academic": academic,
        "lms": lms,
        "cases": cases,
        "recommendations": recs,
        "demo": False,
    }


def load_bundle(session_state, teacher_id=None):
    return _real_bundle(teacher_id)


def _open_mentored_ids():
    if not store.available("mentorships"):
        return set()
    try:
        rows = supabase.table("mentorships").select("student_id").in_(
            "status", ["ASSIGNED", "ANONYMOUS_ACTIVE", "FEEDBACK_PENDING", "ACCEPTED", "IDENTITIES_REVEALED"]
        ).execute().data or []
        return {int(r["student_id"]) for r in rows if r.get("student_id") is not None}
    except Exception:
        return set()


def logs_by_student(bundle):
    grouped = defaultdict(list)
    for r in bundle.get("logs") or []:
        grouped[r.get("student_id")].append(r)
    return grouped


def profile_map(bundle):
    logs_by = logs_by_student(bundle)
    aca_by = defaultdict(list)
    lms_by = defaultdict(list)
    for r in bundle.get("academic") or []:
        aca_by[r.get("student_id")].append(r)
    for r in bundle.get("lms") or []:
        lms_by[r.get("student_id")].append(r)
    mentored = _open_mentored_ids() if not bundle.get("demo") else set()
    overdue = set()
    now = datetime.now()
    for c in bundle.get("cases") or []:
        if c.get("status") != "open":
            continue
        try:
            dl = datetime.fromisoformat(str(c.get("deadline")).replace("Z", "+00:00")).replace(tzinfo=None)
            if dl < now and c.get("student_id") is not None:
                overdue.add(c["student_id"])
        except Exception:
            pass
    out = []
    for s in bundle.get("students") or []:
        sid = s.get("student_id")
        att = attendance_features(logs_by.get(sid))
        aca = academic_features(aca_by.get(sid))
        eng = engagement_features(lms_by.get(sid))
        support = {"mentorship_active": sid in mentored}
        pred = score_student(att, aca, eng, support=support)
        recs = recommend(pred, att)
        temporal = temporal_features(att)
        pred["temporal"] = temporal
        courses = []
        for e in bundle.get("enrollments") or []:
            if e.get("student_id") == sid:
                sub = e.get("subjects") or {}
                courses.append(sub.get("name") or sub.get("subject_code") or "—")
        out.append({
            "student": s,
            "student_id": sid,
            "name": s.get("name"),
            "courses": sorted(set(courses)),
            "attendance": att,
            "academic": aca,
            "engagement": eng,
            "prediction": pred,
            "recommendations": recs,
            "demo": bundle.get("demo"),
            "velocity": temporal.get("velocity") or 0,
            "category": pred.get("category"),
            "score": pred.get("score"),
            "overdue": sid in overdue,
            "mentorship_active": support["mentorship_active"],
        })
    return prioritize(out)


def student_360(bundle, student_id):
    rows = [p for p in profile_map(bundle) if p["student_id"] == student_id]
    return rows[0] if rows else None


def predict_one(student_id, session_state=None):
    """Authoritative single-student score. Same scorer as profile_map, no class-wide scan."""
    from src.database.config import is_supabase_configured
    from src.database.db import get_student_attendance, get_student_public
    from src.database import local_store as local

    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return None
    if is_supabase_configured():
        student = get_student_public(student_id)
        logs = get_student_attendance(student_id) or []
    else:
        student = local.public_student(local.get_student(student_id))
        logs = local.student_attendance(student_id) or []
    if not student:
        return None
    demo = bool(session_state and session_state.get("demo_mode"))
    academic = [r for r in (store.select("academic_records") or []) if r.get("student_id") == student_id]
    lms = [r for r in (store.select("lms_events") or []) if r.get("student_id") == student_id]
    att = attendance_features(logs)
    aca = academic_features(academic)
    eng = engagement_features(lms)
    mentored = False if demo else (student_id in _open_mentored_ids())
    pred = score_student(att, aca, eng, support={"mentorship_active": mentored})
    temporal = temporal_features(att)
    pred["temporal"] = temporal
    return {
        "student": student,
        "student_id": student_id,
        "name": student.get("name"),
        "courses": [],
        "attendance": att,
        "academic": aca,
        "engagement": eng,
        "prediction": pred,
        "recommendations": recommend(pred, att),
        "demo": demo,
        "velocity": temporal.get("velocity") or 0,
        "category": pred.get("category"),
        "score": pred.get("score"),
        "overdue": False,
        "mentorship_active": mentored,
        "logs": logs,
    }


def library():
    rows = store.select("intervention_library")
    return rows or DEFAULT_LIBRARY
