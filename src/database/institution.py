"""Read-only aggregations over existing enrollments and attendance_logs."""

from collections import defaultdict
from datetime import datetime

from src.auth.guards import require_same_teacher
from src.database.config import supabase, is_supabase_configured
from src.database.db import get_attendance_for_teacher, get_teacher_subjects

REGULAR_MIN = 75
WATCH_MIN = 50


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None


def attendance_rate(present: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(100.0 * present / total, 1)


def attendance_band(rate: float, regular_min=REGULAR_MIN, watch_min=WATCH_MIN) -> str:
    """Attendance bands from is_present logs — not an ML risk model."""
    if rate >= regular_min:
        return "Regular"
    if rate >= watch_min:
        return "Watch"
    return "Critical"


def load_teacher_institution(teacher_id, session_state=None):
    if not require_same_teacher(teacher_id, session_state):
        return {"subjects": [], "records": [], "enrollments": []}

    if not is_supabase_configured():
        from src.database import local_store as local
        subjects = local.teacher_subjects(teacher_id)
        records = local.teacher_attendance(teacher_id)
        enrollments = []
        data = local.read_db()
        owned = {int(s["subject_id"]) for s in subjects}
        students = {int(s["student_id"]): s for s in data.get("students") or []}
        for row in data.get("subject_students") or []:
            if int(row.get("subject_id") or 0) not in owned:
                continue
            student = students.get(int(row.get("student_id") or 0)) or {}
            enrollments.append({
                **row,
                "students": {"student_id": student.get("student_id"), "name": student.get("name")},
            })
        return {"subjects": subjects, "records": records or [], "enrollments": enrollments}

    subjects = get_teacher_subjects(teacher_id)
    records = get_attendance_for_teacher(teacher_id)

    enrollments = []
    if is_supabase_configured() and subjects:
        subject_ids = [s["subject_id"] for s in subjects]
        try:
            res = (
                supabase.table("subject_students")
                .select("student_id, subject_id, students(student_id, name)")
                .in_("subject_id", subject_ids)
                .execute()
            )
            enrollments = res.data or []
        except Exception:
            enrollments = []

    return {
        "subjects": subjects,
        "records": records or [],
        "enrollments": enrollments,
    }


def apply_filters(bundle, subject_id=None, section=None, start_date=None, end_date=None):
    subjects = list(bundle["subjects"])
    if section:
        subjects = [s for s in subjects if s.get("section") == section]
    if subject_id:
        subjects = [s for s in subjects if s.get("subject_id") == subject_id]
    allowed = {s["subject_id"] for s in subjects}

    records = [r for r in bundle["records"] if r.get("subject_id") in allowed]
    if start_date or end_date:
        dated = []
        for r in records:
            dt = _parse_ts(r.get("timestamp"))
            if not dt:
                continue
            day = dt.date()
            if start_date and day < start_date:
                continue
            if end_date and day > end_date:
                continue
            dated.append(r)
        records = dated

    enrollments = [e for e in bundle["enrollments"] if e.get("subject_id") in allowed]
    return {"subjects": subjects, "records": records, "enrollments": enrollments}


def build_metrics(bundle, band_filter=None, regular_min=REGULAR_MIN, watch_min=WATCH_MIN):
    subjects = bundle["subjects"]
    records = bundle["records"]
    enrollments = bundle["enrollments"]
    subject_by_id = {s["subject_id"]: s for s in subjects}

    per_student = defaultdict(lambda: {
        "present": 0,
        "total": 0,
        "name": "",
        "courses": set(),
        "sections": set(),
        "last_ts": None,
        "last_present": None,
    })

    for e in enrollments:
        sid = e.get("student_id")
        student = e.get("students") or {}
        sub = subject_by_id.get(e.get("subject_id")) or {}
        if not sid:
            continue
        per_student[sid]["name"] = student.get("name") or per_student[sid]["name"]
        if sub.get("name"):
            per_student[sid]["courses"].add(sub["name"])
        if sub.get("section"):
            per_student[sid]["sections"].add(sub["section"])

    for r in records:
        sid = r.get("student_id")
        if not sid:
            continue
        per_student[sid]["total"] += 1
        if r.get("is_present"):
            per_student[sid]["present"] += 1
        if not per_student[sid]["name"]:
            per_student[sid]["name"] = f"Student {sid}"
        sub = r.get("subjects") or subject_by_id.get(r.get("subject_id")) or {}
        if sub.get("name"):
            per_student[sid]["courses"].add(sub["name"])
        if sub.get("section"):
            per_student[sid]["sections"].add(sub["section"])
        ts = str(r.get("timestamp") or "")
        if ts and (per_student[sid]["last_ts"] is None or ts > per_student[sid]["last_ts"]):
            per_student[sid]["last_ts"] = ts
            per_student[sid]["last_present"] = bool(r.get("is_present"))

    student_meta = {}
    for sid, row in per_student.items():
        rate = attendance_rate(row["present"], row["total"])
        band = attendance_band(rate, regular_min, watch_min) if row["total"] else None
        student_meta[sid] = {**row, "rate": rate, "band": band}

    if band_filter in ("Regular", "Watch", "Critical"):
        keep = {sid for sid, meta in student_meta.items() if meta["band"] == band_filter}
        records = [r for r in records if r.get("student_id") in keep]
        enrollments = [e for e in enrollments if e.get("student_id") in keep]
        student_meta = {sid: meta for sid, meta in student_meta.items() if sid in keep}

    student_ids = {e.get("student_id") for e in enrollments if e.get("student_id")}
    present = sum(1 for r in records if r.get("is_present"))
    absent = len(records) - present
    sessions = {str(r.get("timestamp")) for r in records if r.get("timestamp")}

    bands = {"Regular": 0, "Watch": 0, "Critical": 0}
    watchlist = []
    for sid, meta in student_meta.items():
        if meta["band"]:
            bands[meta["band"]] += 1
        if meta["band"] in ("Watch", "Critical"):
            last_status = "—"
            if meta["last_present"] is True:
                last_status = "Present"
            elif meta["last_present"] is False:
                last_status = "Absent"
            watchlist.append({
                "student_id": sid,
                "name": meta["name"] or f"Student {sid}",
                "course": ", ".join(sorted(meta["courses"])) or "—",
                "section": ", ".join(sorted(meta["sections"])) or "—",
                "present": meta["present"],
                "total": meta["total"],
                "rate": meta["rate"],
                "band": meta["band"],
                "recent": last_status,
            })
    watchlist.sort(key=lambda x: (x["rate"], x["name"]))

    latest_alerts = []
    if records:
        latest_ts = max((str(r.get("timestamp")) for r in records if r.get("timestamp")), default=None)
        if latest_ts:
            for r in records:
                if str(r.get("timestamp")) != latest_ts or r.get("is_present"):
                    continue
                sid = r.get("student_id")
                meta = student_meta.get(sid, {})
                sub = r.get("subjects") or subject_by_id.get(r.get("subject_id")) or {}
                dt = _parse_ts(latest_ts)
                latest_alerts.append({
                    "name": meta.get("name") or f"Student {sid}",
                    "student_id": sid,
                    "subject": sub.get("name") or "—",
                    "section": sub.get("section") or "—",
                    "time": dt.strftime("%Y-%m-%d %I:%M %p") if dt else latest_ts,
                    "status": "Absent",
                })

    trend = defaultdict(lambda: {"present": 0, "absent": 0, "total": 0})
    for r in records:
        dt = _parse_ts(r.get("timestamp"))
        if not dt:
            continue
        day = dt.date().isoformat()
        trend[day]["total"] += 1
        if r.get("is_present"):
            trend[day]["present"] += 1
        else:
            trend[day]["absent"] += 1
    trend_rows = [
        {
            "date": day,
            "present": v["present"],
            "absent": v["absent"],
            "present_rate": attendance_rate(v["present"], v["total"]),
        }
        for day, v in sorted(trend.items())
    ]

    def _band_counts_for(student_ids_subset):
        counts = {"Watch": 0, "Critical": 0}
        for sid in student_ids_subset:
            band = student_meta.get(sid, {}).get("band")
            if band in counts:
                counts[band] += 1
        return counts

    course_rows = []
    for sub in subjects:
        sid = sub["subject_id"]
        sub_logs = [r for r in records if r.get("subject_id") == sid]
        enrolled_ids = {e.get("student_id") for e in enrollments if e.get("subject_id") == sid}
        p = sum(1 for r in sub_logs if r.get("is_present"))
        band_counts = _band_counts_for(enrolled_ids)
        course_rows.append({
            "Subject": sub.get("name"),
            "Code": sub.get("subject_code"),
            "Section": sub.get("section"),
            "Students": len(enrolled_ids),
            "Present": p,
            "Absent": len(sub_logs) - p,
            "Attendance %": attendance_rate(p, len(sub_logs)) if sub_logs else 0.0,
            "Watch": band_counts["Watch"],
            "Critical": band_counts["Critical"],
        })

    section_rows = defaultdict(lambda: {"students": set(), "present": 0, "total": 0})
    for e in enrollments:
        sub = subject_by_id.get(e.get("subject_id"))
        if sub:
            section_rows[sub.get("section") or "—"]["students"].add(e.get("student_id"))
    for r in records:
        sub = r.get("subjects") or subject_by_id.get(r.get("subject_id")) or {}
        key = sub.get("section") or "—"
        section_rows[key]["total"] += 1
        if r.get("is_present"):
            section_rows[key]["present"] += 1
    section_table = []
    for section, v in sorted(section_rows.items()):
        band_counts = _band_counts_for(v["students"])
        section_table.append({
            "Section": section,
            "Students": len(v["students"]),
            "Present": v["present"],
            "Absent": v["total"] - v["present"],
            "Attendance %": attendance_rate(v["present"], v["total"]) if v["total"] else 0.0,
            "Watch": band_counts["Watch"],
            "Critical": band_counts["Critical"],
        })

    return {
        "student_count": len(student_ids),
        "subject_count": len(subjects),
        "session_count": len(sessions),
        "present": present,
        "absent": absent,
        "overall_rate": attendance_rate(present, len(records)) if records else 0.0,
        "bands": bands,
        "critical_count": bands["Critical"],
        "watchlist": watchlist,
        "alerts": latest_alerts,
        "trend": trend_rows,
        "courses": course_rows,
        "sections": section_table,
        "regular_min": regular_min,
        "watch_min": watch_min,
    }
