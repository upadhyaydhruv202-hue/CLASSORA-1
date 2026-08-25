"""Idempotent CLASSORA prototype demo seed.

Synthetic records only. Does not write face/voice embeddings, does not
touch the performance-ML pipeline, and does not invent schema columns.
Derived metrics (attendance %, averages, risk, wallets) stay with existing
CLASSORA calculators.
"""

from __future__ import annotations

import hashlib
import random
from datetime import datetime, timedelta, timezone
from typing import Any

from src.database.config import is_supabase_configured, supabase
from src.database import db
from src.database import local_store as local
from src.success import store
from src.success.risk_model import academic_features, attendance_features, engagement_features

DEMO_MARK = "(Demo)"
DEMO_ASSESSMENT_PREFIX = "Demo · "
DEMO_LMS_COURSE = "DEMO-HUB"
DEMO_ALERT_SOURCE = "demo_seed"
DEMO_SECTION = "Demo"
ATTENDANCE_WEEKS = 10
ASSESSMENTS = ("Midterm", "Assignment", "Quiz", "Project")
SEMESTERS = ("Demo S1", "Demo S2")

SUBJECTS = (
    {"code": "DEMO-CS101", "name": "Data Structures"},
    {"code": "DEMO-MA102", "name": "Discrete Mathematics"},
    {"code": "DEMO-PH103", "name": "Digital Logic"},
    {"code": "DEMO-EN104", "name": "Technical Communication"},
)

COMMUNITIES = (
    {
        "slug": "demo-coding-club",
        "name": "Demo Coding Club",
        "category_code": "TECHNICAL",
        "description": "Prototype community for CLASSORA feature demonstration.",
        "purpose": "Share practice problems and hackathon notes.",
        "members": ("AARAV", "ANANYA", "NEIL", "SARA", "TARA"),
        "posts": (
            ("AARAV", "POST", "[Demo] Weekly problem set is up — stacks and recursion."),
            ("NEIL", "POST", "[Demo] Looking for a teammate for the campus hackathon practice round."),
            ("SARA", "ANNOUNCEMENT", "[Demo] Office-hours style debug session Friday evening."),
        ),
    },
    {
        "slug": "demo-sports-circle",
        "name": "Demo Sports Circle",
        "category_code": "SPORTS",
        "description": "Prototype sports community for demonstration only.",
        "purpose": "Practice fixtures and volunteering at campus events.",
        "members": ("ANANYA", "VIHAAN", "TARA", "ZARA"),
        "posts": (
            ("ANANYA", "POST", "[Demo] Badminton doubles practice tomorrow after classes."),
            ("ZARA", "POST", "[Demo] Volunteers needed for the cultural warmup match."),
        ),
    },
    {
        "slug": "demo-cultural-circle",
        "name": "Demo Cultural Circle",
        "category_code": "CULTURAL",
        "description": "Prototype cultural community.",
        "purpose": "Festival practice and volunteering.",
        "members": ("ZARA", "SARA", "TARA"),
        "posts": (
            ("ZARA", "POST", "[Demo] Cultural rehearsal notes are in the shared folder."),
        ),
    },
    {
        "slug": "demo-academic-study",
        "name": "Demo Academic Study Group",
        "category_code": "ACADEMIC",
        "description": "Prototype academic community.",
        "purpose": "Peer notes for DEMO-CS101.",
        "members": ("AARAV", "DIYA", "ROHAN"),
        "posts": (
            ("AARAV", "POST", "[Demo] Midterm revision checklist for Data Structures."),
        ),
    },
    {
        "slug": "demo-campus-activities",
        "name": "Demo Campus Activities",
        "category_code": "ACTIVITIES",
        "description": "Prototype activities community.",
        "purpose": "Campus volunteering and practice events.",
        "members": ("ANANYA", "NEIL", "MEERA"),
        "posts": (
            ("ANANYA", "POST", "[Demo] Sign-up sheet for this week's campus activity hour."),
        ),
    },
    {
        "slug": "demo-festive-committee",
        "name": "Demo Festive Committee",
        "category_code": "FESTIVE",
        "description": "Prototype festive community.",
        "purpose": "Festival planning notes for demonstration.",
        "members": ("ZARA", "SARA", "ANANYA"),
        "posts": (
            ("ZARA", "POST", "[Demo] Festival booth checklist is in the shared folder."),
        ),
    },
)

# Positive IDs only. Names are fictional and labeled as demo.
COHORT = (
    {
        "key": "AARAV",
        "name": "Aarav Mehta (Demo)",
        "persona": "High performer",
        "attendance_rate": 95,
        "attendance_mode": "stable",
        "academic_avg": 88,
        "academic_mode": "stable",
        "lms_count": 28,
        "lms_gap_days": 1,
        "backlogs": 0,
        "mentorship": "light",
        "case": False,
        "context": "Prototype high-engagement profile. Not an institutional record.",
        "rewards": (
            {"category": "ACADEMIC_IMPROVEMENT", "achievement_type": "IMPROVEMENT", "achievement_level": "INSTITUTIONAL", "title": "Demo · Consistent internals", "points": 100},
            {"category": "PROJECT", "achievement_type": "COMPLETED", "achievement_level": "INSTITUTIONAL", "title": "Demo · Course project completed", "points": 100},
            {"category": "HACKATHON", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · Hackathon participation", "points": 100},
        ),
    },
    {
        "key": "DIYA",
        "name": "Diya Shah (Demo)",
        "persona": "Average performer",
        "attendance_rate": 78,
        "attendance_mode": "stable",
        "academic_avg": 72,
        "academic_mode": "stable",
        "lms_count": 14,
        "lms_gap_days": 4,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype mid-range profile.",
        "rewards": (
            {"category": "ATTENDANCE", "achievement_type": "IMPROVEMENT", "achievement_level": "INSTITUTIONAL", "title": "Demo · Attendance recovery week", "points": 75},
        ),
    },
    {
        "key": "KABIR",
        "name": "Kabir Patel (Demo)",
        "persona": "At-risk",
        "attendance_rate": 58,
        "attendance_mode": "decline",
        "academic_avg": 48,
        "academic_mode": "decline",
        "lms_count": 5,
        "lms_gap_days": 18,
        "backlogs": 2,
        "mentorship": "regular",
        "case": True,
        "context": "Prototype declining attendance and internals. For demonstration of support workflows.",
        "rewards": (),
    },
    {
        "key": "MEERA",
        "name": "Meera Iyer (Demo)",
        "persona": "High attendance / average academics",
        "attendance_rate": 93,
        "attendance_mode": "stable",
        "academic_avg": 68,
        "academic_mode": "stable",
        "lms_count": 12,
        "lms_gap_days": 3,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype: presence is strong while internals stay average.",
        "rewards": (
            {"category": "ATTENDANCE", "achievement_type": "IMPROVEMENT", "achievement_level": "INSTITUTIONAL", "title": "Demo · Strong presence streak", "points": 75},
        ),
    },
    {
        "key": "ROHAN",
        "name": "Rohan Desai (Demo)",
        "persona": "High academics / low engagement",
        "attendance_rate": 82,
        "attendance_mode": "stable",
        "academic_avg": 91,
        "academic_mode": "stable",
        "lms_count": 3,
        "lms_gap_days": 21,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype: strong scores with sparse LMS activity.",
        "rewards": (
            {"category": "PROJECT", "achievement_type": "COMPLETED", "achievement_level": "INSTITUTIONAL", "title": "Demo · Independent project", "points": 100},
        ),
    },
    {
        "key": "ANANYA",
        "name": "Ananya Reddy (Demo)",
        "persona": "Active extracurricular",
        "attendance_rate": 85,
        "attendance_mode": "stable",
        "academic_avg": 76,
        "academic_mode": "stable",
        "lms_count": 16,
        "lms_gap_days": 2,
        "backlogs": 0,
        "mentorship": "light",
        "case": False,
        "context": "Prototype sports and community activity alongside coursework.",
        "rewards": (
            {"category": "SPORTS", "achievement_type": "PARTICIPATION", "achievement_level": "INTER_COLLEGE", "title": "Demo · Inter-college badminton", "points": 100},
            {"category": "VOLUNTEERING", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · Event volunteering", "points": 75},
        ),
    },
    {
        "key": "VIHAAN",
        "name": "Vihaan Kapoor (Demo)",
        "persona": "Attendance slipping",
        "attendance_rate": 64,
        "attendance_mode": "decline",
        "academic_avg": 70,
        "academic_mode": "stable",
        "lms_count": 8,
        "lms_gap_days": 9,
        "backlogs": 0,
        "mentorship": "regular",
        "case": True,
        "context": "Prototype sudden attendance decline with otherwise average internals.",
        "rewards": (),
    },
    {
        "key": "SARA",
        "name": "Sara Khan (Demo)",
        "persona": "Strong engagement, moderate grades",
        "attendance_rate": 80,
        "attendance_mode": "stable",
        "academic_avg": 74,
        "academic_mode": "stable",
        "lms_count": 24,
        "lms_gap_days": 0,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype high LMS activity with mid-range scores.",
        "rewards": (
            {"category": "LEADERSHIP", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · Club coordinator", "points": 100},
        ),
    },
    {
        "key": "ISHAAN",
        "name": "Ishaan Nair (Demo)",
        "persona": "Backlogs with mentorship",
        "attendance_rate": 71,
        "attendance_mode": "stable",
        "academic_avg": 52,
        "academic_mode": "stable",
        "lms_count": 9,
        "lms_gap_days": 6,
        "backlogs": 1,
        "mentorship": "regular",
        "case": True,
        "context": "Prototype backlog plus open support case.",
        "rewards": (),
    },
    {
        "key": "TARA",
        "name": "Tara Bose (Demo)",
        "persona": "Stable average",
        "attendance_rate": 84,
        "attendance_mode": "stable",
        "academic_avg": 75,
        "academic_mode": "stable",
        "lms_count": 11,
        "lms_gap_days": 5,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype stable mid-range student.",
        "rewards": (),
    },
    {
        "key": "NEIL",
        "name": "Neil Joshi (Demo)",
        "persona": "Hackathon / rewards heavy",
        "attendance_rate": 81,
        "attendance_mode": "stable",
        "academic_avg": 79,
        "academic_mode": "stable",
        "lms_count": 18,
        "lms_gap_days": 2,
        "backlogs": 0,
        "mentorship": "light",
        "case": False,
        "context": "Prototype innovation-activity profile.",
        "rewards": (
            {"category": "HACKATHON", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · Campus hackathon", "points": 100},
            {"category": "PROJECT", "achievement_type": "COMPLETED", "achievement_level": "INSTITUTIONAL", "title": "Demo · Innovation showcase project", "points": 100},
        ),
    },
    {
        "key": "ZARA",
        "name": "Zara Qureshi (Demo)",
        "persona": "Cultural and volunteering",
        "attendance_rate": 87,
        "attendance_mode": "stable",
        "academic_avg": 77,
        "academic_mode": "stable",
        "lms_count": 13,
        "lms_gap_days": 3,
        "backlogs": 0,
        "mentorship": "none",
        "case": False,
        "context": "Prototype cultural / volunteering profile.",
        "rewards": (
            {"category": "VOLUNTEERING", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · Community volunteering", "points": 75},
            {"category": "NSS", "achievement_type": "PARTICIPATION", "achievement_level": "INSTITUTIONAL", "title": "Demo · NSS participation", "points": 75},
        ),
    },
)


def historical_cohort() -> tuple:
    """Extra labeled students so dropout RCA has enough explicit outcomes."""
    rows = []
    drop = (
        ("DROPPED_OUT", 6, 46, 36),
        ("WITHDRAWN", 2, 58, 48),
        ("DISCONTINUED", 2, 52, 42),
        ("GRADUATED", 4, 91, 84),
        ("ACTIVE", 2, 80, 71),
    )
    n = 0
    for status, count, att, aca in drop:
        for i in range(1, count + 1):
            n += 1
            rows.append({
                "key": f"HIST_{n:02d}",
                "name": f"Historical {status.title().replace('_', ' ')} {i:02d} (Demo)",
                "persona": f"Historical {status}",
                "attendance_rate": att + (i % 5),
                "attendance_mode": "decline" if status in ("DROPPED_OUT", "WITHDRAWN", "DISCONTINUED") else "stable",
                "academic_avg": aca + (i % 4),
                "academic_mode": "decline" if status in ("DROPPED_OUT", "DISCONTINUED") else "stable",
                "lms_count": 4 if status in ("DROPPED_OUT", "WITHDRAWN", "DISCONTINUED") else 12,
                "lms_gap_days": 20 if status in ("DROPPED_OUT", "WITHDRAWN", "DISCONTINUED") else 3,
                "backlogs": 1 if status in ("DROPPED_OUT", "DISCONTINUED") else 0,
                "mentorship": "none",
                "case": False,
                "context": f"Prototype historical outcome {status}. Not an institutional record.",
                "rewards": (),
                "outcome": status,
            })
    return tuple(rows)


def is_demo_student_name(name: str) -> bool:
    text = str(name or "")
    return DEMO_MARK in text or text.startswith("Demo ·")


def _rng(seed: str) -> random.Random:
    digest = hashlib.sha256(f"classora-demo-seed:{seed}".encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime | None = None) -> str:
    return (value or _now()).isoformat()


def _cloud() -> bool:
    return is_supabase_configured()


def _first(result):
    if not result:
        return None
    if isinstance(result, list):
        return result[0] if result else None
    return result


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def present_mask(total: int, target_rate: int, rng: random.Random, mode: str = "stable") -> list[bool]:
    """Build a present/absent sequence whose mean matches target_rate."""
    total = max(1, int(total))
    present_n = int(round(total * float(target_rate) / 100.0))
    present_n = min(total, max(0, present_n))
    mask = [True] * present_n + [False] * (total - present_n)
    if mode == "decline" and total >= 4:
        mid = total // 2
        early_present = min(present_n, int(round(mid * 0.88)))
        late_present = present_n - early_present
        early = [True] * early_present + [False] * (mid - early_present)
        late = [True] * max(0, late_present) + [False] * (total - mid - max(0, late_present))
        rng.shuffle(early)
        rng.shuffle(late)
        return early + late
    rng.shuffle(mask)
    return mask


def attendance_sessions(now: datetime | None = None) -> list[tuple[int, datetime]]:
    """(subject_index, timestamp) oldest → newest. One class per subject per week."""
    stamp = now or _now()
    out = []
    for week in range(ATTENDANCE_WEEKS, 0, -1):
        monday = (stamp - timedelta(days=stamp.weekday(), weeks=week - 1)).replace(
            hour=10, minute=15, second=0, microsecond=0
        )
        for subject_index in range(len(SUBJECTS)):
            when = monday + timedelta(days=subject_index, hours=subject_index)
            out.append((subject_index, when))
    return out


def build_attendance_logs(profile: dict, subject_ids: list[int], now: datetime | None = None) -> list[dict]:
    sessions = attendance_sessions(now)
    rng = _rng(f"att:{profile['key']}")
    mask = present_mask(len(sessions), profile["attendance_rate"], rng, profile.get("attendance_mode") or "stable")
    logs = []
    for (subject_index, when), present in zip(sessions, mask):
        logs.append({
            "student_id": profile["student_id"],
            "subject_id": subject_ids[subject_index],
            "timestamp": _iso(when),
            "is_present": bool(present),
        })
    return logs


def _score_for(profile: dict, semester: str, assessment: str, subject_index: int) -> float:
    rng = _rng(f"aca:{profile['key']}:{semester}:{assessment}:{subject_index}")
    target = float(profile["academic_avg"])
    if profile.get("academic_mode") == "decline":
        target = target + 10 if semester == SEMESTERS[0] else target - 10
    spread = 7.0 if profile["persona"] != "At-risk" else 11.0
    score = target + rng.uniform(-spread, spread) + (subject_index - 1.5)
    if assessment == "Project":
        score += 2
    if assessment == "Quiz":
        score -= 1
    lo, hi = (18, 96) if profile.get("backlogs") else (42, 99)
    return round(min(hi, max(lo, score)), 1)


def build_academic_records(profile: dict, subject_ids: list[int], now: datetime | None = None) -> list[dict]:
    stamp = now or _now()
    rows = []
    remaining_backlogs = int(profile.get("backlogs") or 0)
    for sem_i, semester in enumerate(SEMESTERS):
        for subject_index, subject_id in enumerate(subject_ids):
            for assessment in ASSESSMENTS:
                score = _score_for(profile, semester, assessment, subject_index)
                backlog = False
                if remaining_backlogs and score < 45 and semester == SEMESTERS[-1]:
                    backlog = True
                    remaining_backlogs -= 1
                    score = min(score, 38)
                recorded = stamp - timedelta(days=70 - sem_i * 30 - subject_index * 2)
                rows.append({
                    "student_id": profile["student_id"],
                    "subject_id": subject_id,
                    "semester": semester,
                    "assessment": f"{DEMO_ASSESSMENT_PREFIX}{assessment}",
                    "score": score,
                    "max_score": 100,
                    "gpa": round(score / 10.0, 2),
                    "backlog": backlog,
                    "recorded_at": _iso(recorded),
                })
    return rows


def build_lms_events(profile: dict, now: datetime | None = None) -> list[dict]:
    stamp = now or _now()
    rng = _rng(f"lms:{profile['key']}")
    kinds = ("login", "assignment_submit", "resource_view", "quiz_attempt", "discussion")
    gap = int(profile.get("lms_gap_days") or 0)
    count = int(profile.get("lms_count") or 0)
    events = []
    for i in range(count):
        days_ago = gap + i * max(1, int(round(18 / max(count, 1))))
        jitter = rng.randint(0, 10)
        when = stamp - timedelta(days=days_ago, hours=jitter)
        events.append({
            "student_id": profile["student_id"],
            "event_type": kinds[i % len(kinds)],
            "course_code": DEMO_LMS_COURSE,
            "occurred_at": _iso(when),
        })
    return events


def expected_attendance_rate(profile: dict) -> float:
    sessions = attendance_sessions()
    rng = _rng(f"att:{profile['key']}")
    mask = present_mask(len(sessions), profile["attendance_rate"], rng, profile.get("attendance_mode") or "stable")
    return round(100.0 * sum(1 for bit in mask if bit) / len(mask), 1)


def _list_students() -> list[dict]:
    if _cloud():
        return db.get_all_students("student_id, name") or []
    return [{"student_id": row.get("student_id"), "name": row.get("name")} for row in local.read_db().get("students") or []]


def _list_teachers() -> list[dict]:
    if _cloud():
        try:
            return supabase.table("teachers").select("teacher_id, username, name").execute().data or []
        except Exception:
            return []
    return [
        {"teacher_id": row.get("teacher_id"), "username": row.get("username"), "name": row.get("name")}
        for row in local.read_db().get("teachers") or []
    ]


def _list_subjects() -> list[dict]:
    if _cloud():
        try:
            return supabase.table("subjects").select("subject_id, subject_code, name, section, teacher_id").execute().data or []
        except Exception:
            return []
    return list(local.read_db().get("subjects") or [])


def _insert_student(name: str) -> dict | None:
    if _cloud():
        try:
            data = supabase.table("students").insert({"name": name}).execute().data or []
            return _first(data)
        except Exception:
            return None
    return local.create_student(name)


def _insert_subject(code: str, name: str, teacher_id: int) -> dict | None:
    if _cloud():
        try:
            return _first(db.create_subject(code, name, DEMO_SECTION, teacher_id))
        except Exception:
            return None
    return local.create_subject(code, name, DEMO_SECTION, teacher_id)


def _enroll(student_id: int, subject_id: int) -> None:
    if _cloud():
        try:
            db.enroll_student_to_subject(student_id, subject_id)
        except Exception:
            pass
        return
    local.enroll(student_id, subject_id)


def _insert_attendance(logs: list[dict]) -> int:
    if not logs:
        return 0
    if _cloud():
        saved = 0
        for start in range(0, len(logs), 80):
            chunk = logs[start:start + 80]
            try:
                data = db.create_attendance(chunk) or []
                saved += len(data)
            except Exception:
                for row in chunk:
                    try:
                        data = db.create_attendance([row]) or []
                        saved += len(data)
                    except Exception:
                        pass
        return saved
    data = local.add_attendance(logs) or []
    return len(data)


def _existing_demo_attendance(student_id: int, subject_ids: list[int]) -> bool:
    if not subject_ids:
        return False
    if _cloud():
        try:
            rows = (
                supabase.table("attendance_logs")
                .select("id")
                .eq("student_id", student_id)
                .in_("subject_id", subject_ids)
                .limit(1)
                .execute()
                .data
                or []
            )
            return bool(rows)
        except Exception:
            return False
    ids = set(subject_ids)
    for row in local.read_db().get("attendance_logs") or []:
        if _int(row.get("student_id")) == int(student_id) and _int(row.get("subject_id")) in ids:
            return True
    return False


def _has_demo_academics(student_id: int) -> bool:
    rows = store.select("academic_records", student_id=student_id) or []
    return any(str(row.get("assessment") or "").startswith(DEMO_ASSESSMENT_PREFIX) for row in rows)


def _has_demo_lms(student_id: int) -> bool:
    rows = store.select("lms_events", student_id=student_id) or []
    return any(str(row.get("course_code") or "") == DEMO_LMS_COURSE for row in rows)


def _insert_many(table: str, rows: list[dict]) -> int:
    created = 0
    if _cloud() and rows:
        for start in range(0, len(rows), 60):
            chunk = rows[start:start + 60]
            try:
                data = supabase.table(table).insert(chunk).execute().data or []
                created += len(data)
                continue
            except Exception:
                pass
            for row in chunk:
                saved = store.insert(table, row)
                created += len(saved or [])
        return created
    for row in rows:
        saved = store.insert(table, row)
        created += len(saved or [])
    return created


def _ensure_students() -> dict[str, dict]:
    existing = {str(row.get("name")): row for row in _list_students()}
    out = {}
    created = 0
    reused = 0
    for spec in list(COHORT) + list(historical_cohort()):
        row = existing.get(spec["name"])
        if not row:
            row = _insert_student(spec["name"])
            created += 1
        else:
            reused += 1
        if not row:
            continue
        profile = dict(spec)
        profile["student_id"] = _int(row.get("student_id"))
        out[spec["key"]] = profile
    return {"by_key": out, "created": created, "reused": reused}


def _ensure_subjects() -> dict[str, Any]:
    teachers = _list_teachers()
    teacher = _first(teachers)
    existing = {str(row.get("subject_code")): row for row in _list_subjects()}
    subjects = []
    created = 0
    if not teacher:
        return {"subjects": [], "teacher": None, "created": 0, "skipped": "no_teacher"}
    teacher_id = _int(teacher.get("teacher_id"))
    for spec in SUBJECTS:
        row = existing.get(spec["code"])
        if not row:
            row = _insert_subject(spec["code"], spec["name"], teacher_id)
            created += 1
        if row:
            subjects.append(row)
    return {"subjects": subjects, "teacher": teacher, "created": created, "skipped": None}


def _seed_classroom(profiles: dict[str, dict], subjects: list[dict], counts: dict) -> None:
    subject_ids = [_int(row.get("subject_id")) for row in subjects if _int(row.get("subject_id")) is not None]
    if not subject_ids:
        counts["attendance_skipped"] = "no_demo_subjects"
        return
    for profile in profiles.values():
        sid = profile["student_id"]
        for subject_id in subject_ids:
            _enroll(sid, subject_id)
            counts["enrollments"] += 1
        if _existing_demo_attendance(sid, subject_ids):
            counts["attendance_skipped_existing"] += 1
            continue
        logs = build_attendance_logs(profile, subject_ids)
        counts["attendance"] += _insert_attendance(logs)


def _seed_academics(profiles: dict[str, dict], subjects: list[dict], counts: dict) -> None:
    subject_ids = [_int(row.get("subject_id")) for row in subjects if _int(row.get("subject_id")) is not None]
    if not subject_ids:
        subject_ids = [None] * len(SUBJECTS)
    for profile in profiles.values():
        if _has_demo_academics(profile["student_id"]):
            counts["academic_skipped_existing"] += 1
            continue
        rows = build_academic_records(profile, subject_ids)
        counts["academic"] += _insert_many("academic_records", rows)


def _seed_lms(profiles: dict[str, dict], counts: dict) -> None:
    for profile in profiles.values():
        if _has_demo_lms(profile["student_id"]):
            counts["lms_skipped_existing"] += 1
            continue
        rows = build_lms_events(profile)
        counts["lms"] += _insert_many("lms_events", rows)


def _seed_support(profiles: dict[str, dict], counts: dict) -> None:
    from src.success.notify import notify

    for profile in profiles.values():
        sid = profile["student_id"]
        if not (store.select("student_context", student_id=sid) or []):
            saved = store.insert("student_context", {
                "student_id": sid,
                "workload_note": profile.get("context") or "",
                "digital_access": "Demo seed — not a live access survey.",
                "self_report": "Prototype dataset only.",
                "minimized": True,
                "updated_at": _iso(),
            })
            counts["context"] += len(saved or [])
        if profile.get("case"):
            code = f"CASE-DEMO-{profile['key']}"
            existing = [row for row in (store.select("intervention_cases") or []) if row.get("case_code") == code]
            if not existing:
                saved = store.insert("intervention_cases", {
                    "case_code": code,
                    "student_id": sid,
                    "owner": "Counsellor (Demo seed)",
                    "priority": "high" if profile["key"] == "KABIR" else "medium",
                    "status": "open",
                    "intervention_name": "Attendance check-in" if profile["attendance_mode"] == "decline" else "Academic tutoring referral",
                    "deadline": _iso(_now() + timedelta(days=5)),
                    "notes": "Prototype demonstration case. Not an institutional file.",
                })
                counts["cases"] += len(saved or [])
            recs = store.select("intervention_recommendations", student_id=sid) or []
            if not any("Demo seed" in str(row.get("reason") or "") for row in recs):
                saved = store.insert("intervention_recommendations", {
                    "student_id": sid,
                    "recommendation": "Mentor weekly meeting",
                    "reason": "Demo seed: associated support signals, not a diagnosis.",
                    "confidence": 0.62,
                    "status": "pending",
                })
                counts["recommendations"] += len(saved or [])
            if not (store.select("recovery_plans", student_id=sid) or []):
                plan = store.insert("recovery_plans", {
                    "student_id": sid,
                    "title": "Demo · Weekly recovery plan",
                    "weekly_plan": "Check attendance twice, complete one missed assignment, meet mentor.",
                    "created_by": "demo_seed",
                })
                counts["recovery_plans"] += len(plan or [])
                plan_id = (_first(plan) or {}).get("id")
                store.insert("recovery_tasks", {
                    "plan_id": plan_id,
                    "student_id": sid,
                    "task": "Attend the next two scheduled classes",
                    "done": False,
                })
                store.insert("recovery_tasks", {
                    "plan_id": plan_id,
                    "student_id": sid,
                    "task": "Submit the outstanding Demo · Assignment",
                    "done": False,
                })
                counts["recovery_tasks"] += 2
            if not (store.select("appointments", student_id=sid) or []):
                saved = store.insert("appointments", {
                    "student_id": sid,
                    "staff_name": "Counsellor (Demo seed)",
                    "kind": "check_in",
                    "starts_at": _iso(_now() + timedelta(days=2, hours=3)),
                    "status": "requested",
                    "notes": "Prototype appointment row.",
                })
                counts["appointments"] += len(saved or [])
        alerts = store.select("alerts", student_id=sid) or []
        if profile.get("case") and not any(row.get("source") == DEMO_ALERT_SOURCE for row in alerts):
            saved = store.insert("alerts", {
                "student_id": sid,
                "source": DEMO_ALERT_SOURCE,
                "severity": "high" if profile["key"] == "KABIR" else "medium",
                "title": "Demo · Attendance / academic support signal",
                "status": "open",
                "owner": "Counsellor (Demo seed)",
            })
            counts["alerts"] += len(saved or [])
            notify(
                role="counsellor",
                recipient_id="caseload",
                title="[Demo] Support signal on caseload",
                body=f"{profile['name']} has prototype support records. Not an institutional alert.",
            )
            notify(
                role="student",
                recipient_id=sid,
                title="[Demo] Support check-in available",
                body="A prototype support case and recovery tasks are visible on My Progress.",
            )
            counts["notifications"] += 2


def _ensure_mentor_profile(staff_id: int | None = None) -> int | None:
    staff_rows = store.select("staff_users") or []
    if staff_id is None:
        eligible = [
            row for row in staff_rows
            if str(row.get("role") or "") in ("faculty", "mentor", "counsellor")
        ]
        if not eligible:
            return None
        staff_id = _int(eligible[0].get("staff_id"))
    if staff_id is None:
        return None
    profiles = store.select("mentor_profiles") or []
    if not any(_int(row.get("staff_id")) == staff_id for row in profiles):
        store.insert("mentor_profiles", {
            "staff_id": staff_id,
            "expertise": "Demo seed mentor profile",
            "available": True,
            "max_caseload": 16,
            "updated_at": _iso(),
        })
    return staff_id


def _staff_id_by_username(username: str) -> int | None:
    for row in store.select("staff_users") or []:
        if str(row.get("username") or "") == username:
            return _int(row.get("staff_id"))
    return None


def _seed_mentorship(profiles: dict[str, dict], counts: dict) -> None:
    from src.mentorship import service as mentorship

    if not mentorship.installed():
        counts["mentorship_skipped"] = "schema_unavailable"
        return
    mentor_id = _ensure_mentor_profile(_staff_id_by_username("DEMO_MENTOR_01")) or _ensure_mentor_profile()
    counsellor_id = _ensure_mentor_profile(_staff_id_by_username("DEMO_COUNSELLOR_01"))
    if mentor_id is None:
        counts["mentorship_skipped"] = "no_staff_mentor"
        return
    wanted = [p for p in profiles.values() if p.get("mentorship") in ("light", "regular")]
    for profile in wanted:
        sid = profile["student_id"]
        view, msg = mentorship.assign_mentorship(
            sid,
            "administrator",
            "demo_seed",
            goal="Prototype mentoring thread for demonstration.",
            risk_band="Support" if profile["mentorship"] == "light" else "Watch",
            kind="mentor",
            prefer_staff_id=mentor_id,
        )
        if not view:
            if msg and "already has" in str(msg).lower():
                counts["mentorships_existing"] = counts.get("mentorships_existing", 0) + 1
                continue
            counts["mentorship_assign_failed"] += 1
            counts.setdefault("mentorship_errors", []).append(f"{profile['key']}: {msg}")
            continue
        if msg and "already" in str(msg).lower():
            counts["mentorships_existing"] = counts.get("mentorships_existing", 0) + 1
            continue
        mid = view.get("mentorshipId")
        counts["mentorships"] += 1
        existing_sessions = store.select("mentorship_sessions") or []
        already = [row for row in existing_sessions if str(row.get("mentorship_id")) == str(mid)]
        if already:
            continue
        n_sessions = 1 if profile["mentorship"] == "light" else 3
        for i in range(n_sessions):
            store.insert("mentorship_sessions", {
                "mentorship_id": mid,
                "title": f"Demo · Session {i + 1}",
                "notes": "Prototype session notes. Not a counselling transcript.",
                "created_by_role": "mentor" if i % 2 == 0 else "student",
            })
            counts["mentorship_sessions"] += 1
        store.insert("mentorship_messages", {
            "mentorship_id": mid,
            "sender_role": "mentor",
            "body": "Demo message: this is a prototype anonymous thread, not a live counselling record.",
        })
        store.insert("mentorship_messages", {
            "mentorship_id": mid,
            "sender_role": "student",
            "body": "Demo reply: checking in on attendance and the next assignment.",
        })
        counts["mentorship_messages"] += 2
    counselling_keys = {"KABIR", "DIYA", "VIHAAN"}
    if counsellor_id:
        for key in counselling_keys:
            profile = profiles.get(key)
            if not profile:
                continue
            view, msg = mentorship.assign_mentorship(
                profile["student_id"],
                "administrator",
                "demo_seed",
                goal="Prototype counselling thread. Separate from mentoring.",
                risk_band="Watch",
                kind="counsellor",
                prefer_staff_id=counsellor_id,
            )
            if not view:
                if msg and "already has" in str(msg).lower():
                    counts["counselling_existing"] = counts.get("counselling_existing", 0) + 1
                    continue
                counts["counselling_assign_failed"] = counts.get("counselling_assign_failed", 0) + 1
                counts.setdefault("mentorship_errors", []).append(f"counsel:{key}: {msg}")
                continue
            if msg and "already" in str(msg).lower():
                counts["counselling_existing"] = counts.get("counselling_existing", 0) + 1
                continue
            mid = view.get("mentorshipId")
            counts["counselling"] = counts.get("counselling", 0) + 1
            existing_sessions = store.select("mentorship_sessions") or []
            already = [row for row in existing_sessions if str(row.get("mentorship_id")) == str(mid)]
            if already:
                continue
            store.insert("mentorship_sessions", {
                "mentorship_id": mid,
                "title": "Demo · Counselling session 1",
                "notes": "Prototype counselling notes. Separate workflow from mentoring.",
                "created_by_role": "mentor",
            })
            store.insert("mentorship_messages", {
                "mentorship_id": mid,
                "sender_role": "mentor",
                "body": "Demo counselling check-in. This thread is counselling, not mentoring.",
            })
            store.insert("mentorship_messages", {
                "mentorship_id": mid,
                "sender_role": "student",
                "body": "Demo reply on the counselling thread.",
            })
            counts["counselling_sessions"] = counts.get("counselling_sessions", 0) + 1
            counts["mentorship_messages"] += 2


def _seed_communities(profiles: dict[str, dict], counts: dict) -> None:
    from src.communities import service as communities

    communities.ensure_seed()
    existing = {str(row.get("slug")): row for row in (store.select("communities") or [])}
    for spec in COMMUNITIES:
        row = existing.get(spec["slug"])
        if not row:
            saved = store.insert("communities", {
                "institution_id": "default",
                "name": spec["name"],
                "slug": spec["slug"],
                "category_code": spec["category_code"],
                "description": spec["description"],
                "purpose": spec["purpose"],
                "rules": "Prototype community. Posts are demonstration data.",
                "tags": ["demo", "prototype"],
                "status": "ACTIVE",
                "created_by": None,
                "approved_by": "demo_seed",
                "approved_at": _iso(),
            })
            row = _first(saved)
            counts["communities"] += len(saved or [])
        if not row:
            continue
        community_id = row.get("id")
        members = store.select("community_members") or []
        for key in spec["members"]:
            profile = profiles.get(key)
            if not profile:
                continue
            sid = profile["student_id"]
            if any(
                str(item.get("community_id")) == str(community_id) and _int(item.get("student_id")) == sid
                for item in members
            ):
                continue
            store.insert("community_members", {
                "community_id": community_id,
                "student_id": sid,
                "role": "COMMUNITY_ADMIN" if key == spec["members"][0] else "MEMBER",
                "status": "ACTIVE",
                "joined_at": _iso(),
            })
            counts["community_members"] += 1
        posts = store.select("community_posts") or []
        if any(str(item.get("community_id")) == str(community_id) and str(item.get("content") or "").startswith("[Demo]") for item in posts):
            continue
        created_posts = []
        for author_key, kind, content in spec["posts"]:
            author = profiles.get(author_key)
            if not author:
                continue
            saved = store.insert("community_posts", {
                "community_id": community_id,
                "author_student_id": author["student_id"],
                "kind": kind,
                "content": content,
                "status": "ACTIVE",
            })
            post = _first(saved)
            if post:
                created_posts.append((post, author_key))
                counts["community_posts"] += 1
        if created_posts:
            post, _author_key = created_posts[0]
            commenter = profiles.get(spec["members"][-1])
            if commenter and post:
                store.insert("community_comments", {
                    "community_id": community_id,
                    "post_id": post.get("id"),
                    "author_student_id": commenter["student_id"],
                    "content": "[Demo] Thanks — this is a prototype comment.",
                    "status": "ACTIVE",
                })
                counts["community_comments"] += 1
                store.insert("community_reactions", {
                    "community_id": community_id,
                    "post_id": post.get("id"),
                    "student_id": commenter["student_id"],
                    "kind": "LIKE",
                })
                counts["community_reactions"] += 1
        events = store.select("community_events") or []
        if not any(str(item.get("community_id")) == str(community_id) and str(item.get("title") or "").startswith("Demo ·") for item in events):
            saved = store.insert("community_events", {
                "community_id": community_id,
                "title": "Demo · Practice meetup",
                "description": "Prototype event. Not a scheduled institutional fixture.",
                "start_at": _iso(_now() + timedelta(days=4)),
                "end_at": _iso(_now() + timedelta(days=4, hours=2)),
                "location": "Demo campus hall",
                "capacity": 24,
                "created_by": profiles[spec["members"][0]]["student_id"] if spec["members"][0] in profiles else None,
                "status": "ACTIVE",
            })
            counts["community_events"] += len(saved or [])


def _seed_rewards(profiles: dict[str, dict], counts: dict) -> None:
    from src.rewards import service as rewards
    from src.rewards import policy as P

    rewards.ensure_seed()
    existing = store.select("reward_achievements") or []
    keys = {str(row.get("idempotency_key") or "") for row in existing}
    for profile in profiles.values():
        sid = profile["student_id"]
        for spec in profile.get("rewards") or ():
            key = f"demo-seed:{profile['key']}:{spec['category']}:{spec['title']}"
            if key in keys:
                counts["rewards_skipped_existing"] += 1
                continue
            saved = store.insert("reward_achievements", {
                "institution_id": "default",
                "student_id": sid,
                "category": spec["category"],
                "achievement_type": spec["achievement_type"],
                "achievement_level": spec["achievement_level"],
                "title": spec["title"],
                "description": "Prototype achievement for CLASSORA demonstration. Not an institutional award.",
                "organization": "CLASSORA Demo Dataset",
                "occurred_at": _iso(_now() - timedelta(days=12)),
                "event_key": spec["title"],
                "evidence": {"note": "demo_seed"},
                "status": P.ACH_APPROVED,
                "proposed_points": spec["points"],
                "awarded_points": spec["points"],
                "policy_ids": [],
                "submitted_by": "demo_seed",
                "submitted_role": "administrator",
                "idempotency_key": key,
            })
            item = _first(saved)
            if not item:
                counts["rewards_failed"] += 1
                continue
            counts["reward_achievements"] += 1
            txn = store.insert("reward_transactions", {
                "institution_id": "default",
                "student_id": sid,
                "transaction_type": P.TX_EARN,
                "points": spec["points"],
                "source_type": "ACHIEVEMENT",
                "source_id": str(item.get("id") or ""),
                "category": spec["category"],
                "description": spec["title"],
                "status": "POSTED",
                "issued_by": "demo_seed",
                "approved_by": "demo_seed",
                "expires_at": _iso(_now() + timedelta(days=180)),
                "metadata": {"demo": True},
            })
            counts["reward_transactions"] += len(txn or [])
            if txn:
                store.update("reward_achievements", {"id": item.get("id")}, {"transaction_id": (_first(txn) or {}).get("id")})
            try:
                rewards._maybe_badge(sid, spec["category"], item.get("id"))
                rewards._maybe_milestones(sid)
            except Exception:
                pass
    badges = store.select("reward_badges") or []
    demo_ids = {profile["student_id"] for profile in profiles.values()}
    counts["reward_badges"] = sum(1 for row in badges if _int(row.get("student_id")) in demo_ids)
    milestones = store.select("reward_milestones") or []
    counts["reward_milestones"] = sum(1 for row in milestones if _int(row.get("student_id")) in demo_ids)


def _empty_counts() -> dict:
    return {
        "students_created": 0,
        "students_reused": 0,
        "subjects_created": 0,
        "enrollments": 0,
        "attendance": 0,
        "attendance_skipped_existing": 0,
        "academic": 0,
        "academic_skipped_existing": 0,
        "lms": 0,
        "lms_skipped_existing": 0,
        "context": 0,
        "alerts": 0,
        "cases": 0,
        "recommendations": 0,
        "recovery_plans": 0,
        "recovery_tasks": 0,
        "appointments": 0,
        "notifications": 0,
        "mentorships": 0,
        "mentorship_sessions": 0,
        "mentorship_messages": 0,
        "mentorship_assign_failed": 0,
        "communities": 0,
        "community_members": 0,
        "community_posts": 0,
        "community_comments": 0,
        "community_reactions": 0,
        "community_events": 0,
        "reward_achievements": 0,
        "reward_transactions": 0,
        "rewards_skipped_existing": 0,
        "rewards_failed": 0,
    }


def seed(now: datetime | None = None) -> dict:
    """Insert/update labeled demo records. Safe to re-run."""
    from src.success import demo_ops

    counts = _empty_counts()
    staff_ids = demo_ops.ensure_staff_accounts(counts)
    teacher = demo_ops.ensure_demo_teacher(counts)
    student_state = _ensure_students()
    profiles = student_state["by_key"]
    counts["students_created"] = student_state["created"]
    counts["students_reused"] = student_state["reused"]
    subject_state = _ensure_subjects()
    counts["subjects_created"] = subject_state["created"]
    subjects = subject_state["subjects"]
    if subject_state.get("skipped"):
        counts["subjects_skipped"] = subject_state["skipped"]
    _seed_classroom(profiles, subjects, counts)
    _seed_academics(profiles, subjects, counts)
    _seed_lms(profiles, counts)
    _seed_support(profiles, counts)
    _seed_mentorship(profiles, counts)
    _seed_communities(profiles, counts)
    _seed_rewards(profiles, counts)
    demo_ops.seed_extras(profiles, counts, staff_ids=staff_ids, teacher=teacher)
    try:
        store.insert("audit_events", {
            "actor": "demo_seed",
            "action": "seed_demo_data",
            "entity": "demo_dataset",
            "detail": f"Prototype demo seed. students={len(profiles)}",
        })
    except Exception:
        pass
    counts["students"] = len(profiles)
    counts["mode"] = "supabase" if _cloud() else "local"
    counts["teacher"] = (subject_state.get("teacher") or {}).get("username")
    counts["demo_teacher"] = demo_ops.DEMO_TEACHER
    counts["credentials_note"] = "See documentation/DEMO.md — DEMO DATA, not real accounts."
    counts["profiles"] = [
        {
            "key": profile["key"],
            "student_id": profile["student_id"],
            "name": profile["name"],
            "persona": profile["persona"],
            "target_attendance": expected_attendance_rate(profile),
            "target_academic": profile["academic_avg"],
            "outcome": profile.get("outcome") or "ACTIVE",
        }
        for profile in profiles.values()
        if not str(profile["key"]).startswith("HIST_")
    ]
    return counts


def coherence_report(profile: dict, subject_ids: list[int] | None = None) -> dict:
    """In-memory check that generated rows match CLASSORA calculators."""
    fake_ids = subject_ids or list(range(1, len(SUBJECTS) + 1))
    sample = dict(profile)
    sample["student_id"] = sample.get("student_id") or 1
    logs = build_attendance_logs(sample, fake_ids)
    academic = build_academic_records(sample, fake_ids)
    lms = build_lms_events(sample)
    att = attendance_features(logs)
    aca = academic_features(academic)
    eng = engagement_features(lms)
    return {
        "key": profile["key"],
        "attendance_rate": att.get("rate"),
        "academic_avg": aca.get("avg_score"),
        "academic_count": aca.get("count"),
        "lms_count": eng.get("count"),
        "attendance_rows": len(logs),
        "academic_rows": len(academic),
        "lms_rows": len(lms),
    }
