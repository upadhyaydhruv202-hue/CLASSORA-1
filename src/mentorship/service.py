"""Anonymous mentorship — identity is enforced here, not in the UI.

Before IDENTITIES_REVEALED, public payloads never include names, emails,
student_id, staff_id, username, department, or embeddings.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from src.database.config import is_supabase_configured, supabase
from src.database.db import get_student_public
from src.success import store
from src.success.staff_auth import get_staff_public

OPEN_STATUSES = ("ASSIGNED", "ANONYMOUS_ACTIVE", "FEEDBACK_PENDING", "REASSIGNMENT_PENDING")
REVEALED_STATUSES = ("ACCEPTED", "IDENTITIES_REVEALED")
ELIGIBLE_MENTOR_ROLES = ("faculty", "mentor", "counsellor")
MAX_DEFAULT_LOAD = 6
CYCLE_DAYS = 7
FEEDBACK_GRACE_DAYS = 7

IDENTITY_KEYS = {
    "student_id",
    "mentor_staff_id",
    "name",
    "username",
    "email",
    "password",
    "face_embedding",
    "voice_embedding",
    "phone",
    "section",
    "subject_code",
}


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def installed() -> bool:
    return store.available("mentorships")


def _demo(session_state) -> bool:
    return bool(session_state.get("demo_mode"))


def _alias(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _audit(actor_role, actor_ref, action, mentorship_id=None, detail=""):
    store.insert("mentorship_audit_logs", {
        "actor_role": actor_role,
        "actor_ref": str(actor_ref or ""),
        "action": action,
        "mentorship_id": mentorship_id,
        "detail": (detail or "")[:500],
    })


def _notify(*, role, title, body, mentorship_id=None, student_id=None, staff_id=None):
    store.insert("mentorship_notifications", {
        "recipient_role": role,
        "recipient_student_id": student_id,
        "recipient_staff_id": staff_id,
        "title": title,
        "body": body,
        "mentorship_id": mentorship_id,
    })


def _fetch(mentorship_id: str):
    if not installed() or not mentorship_id:
        return None
    try:
        rows = supabase.table("mentorships").select("*").eq("mentorship_id", mentorship_id).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _update(mentorship_id: str, values: dict):
    values = {**values, "updated_at": _now().isoformat()}
    return store.update("mentorships", {"mentorship_id": mentorship_id}, values)


def days_remaining(row) -> int:
    due = _parse(row.get("feedback_due_at"))
    if not due:
        return 0
    now = _now()
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    return max(0, (due - now).days)


def tick_lifecycle(session_state=None):
    """Promote ANONYMOUS_ACTIVE → FEEDBACK_PENDING when 7 days elapse."""
    if session_state and _demo(session_state):
        return
    if not installed():
        return
    try:
        rows = supabase.table("mentorships").select("mentorship_id,status,feedback_due_at,student_id,mentor_staff_id,student_alias,mentor_alias").in_(
            "status", ["ASSIGNED", "ANONYMOUS_ACTIVE"]
        ).execute().data or []
    except Exception:
        return
    now = _now()
    for row in rows:
        if row.get("status") == "ASSIGNED":
            _update(row["mentorship_id"], {"status": "ANONYMOUS_ACTIVE"})
            continue
        due = _parse(row.get("feedback_due_at"))
        if not due:
            continue
        if due.tzinfo is None:
            due = due.replace(tzinfo=timezone.utc)
        if due <= now:
            _update(row["mentorship_id"], {"status": "FEEDBACK_PENDING"})
            _notify(
                role="student",
                student_id=row.get("student_id"),
                mentorship_id=row["mentorship_id"],
                title="Feedback available",
                body="Your 7-day anonymous mentorship review is ready. Identities stay hidden until you decide.",
            )
            _notify(
                role="mentor",
                staff_id=row.get("mentor_staff_id"),
                mentorship_id=row["mentorship_id"],
                title="Student feedback pending",
                body=f"Anonymous student {row.get('student_alias')} may now submit a review. Do not expect identity yet.",
            )
            _audit("system", "tick", "feedback_unlocked", row["mentorship_id"])


def _normalize_kind(value) -> str:
    text = str(value or "").strip().lower()
    if text in ("mentor", "mentoring", "mentorship"):
        return "mentor"
    if text in ("counsellor", "counselor", "counselling", "counseling"):
        return "counsellor"
    return ""


def _session_kind(row) -> str:
    if not row:
        return ""
    direct = _normalize_kind(row.get("kind") or row.get("service_kind"))
    if direct:
        return direct
    goal = str(row.get("counseling_goal") or row.get("goal") or "").lower()
    if "mentor" in goal:
        return "mentor"
    if "counsel" in goal:
        return "counsellor"
    staff = get_staff_public(row.get("mentor_staff_id")) or {}
    role = str(staff.get("role") or "").lower()
    if role == "counsellor":
        return "counsellor"
    if role in ("mentor", "faculty"):
        return "mentor"
    return ""


def _open_for_student(student_id):
    try:
        rows = supabase.table("mentorships").select("mentorship_id,status,kind,counseling_goal,mentor_staff_id").eq("student_id", student_id).in_(
            "status", list(OPEN_STATUSES)
        ).execute().data or []
        return rows
    except Exception:
        try:
            return supabase.table("mentorships").select("mentorship_id,status,counseling_goal,mentor_staff_id").eq("student_id", student_id).in_(
                "status", list(OPEN_STATUSES)
            ).execute().data or []
        except Exception:
            return []


def _rejected_pairs(student_id):
    rows = store.select("mentor_assignments", student_id=student_id) or []
    return {int(r["mentor_staff_id"]) for r in rows if r.get("outcome") in ("rejected",) and r.get("mentor_staff_id") is not None}


def _load(mentor_staff_id):
    try:
        rows = supabase.table("mentorships").select("mentorship_id,status").eq("mentor_staff_id", mentor_staff_id).in_(
            "status", list(OPEN_STATUSES) + list(REVEALED_STATUSES)
        ).execute().data or []
        return len(rows)
    except Exception:
        return 0


def _pick_mentor(student_id, prefer_staff_id=None, prefer_roles=None):
    staff = store.select("staff_users") or []
    profiles = {int(p["staff_id"]): p for p in (store.select("mentor_profiles") or []) if p.get("staff_id") is not None}
    blocked = _rejected_pairs(student_id)
    candidates = []
    for s in staff:
        sid = s.get("staff_id")
        if sid is None:
            continue
        sid = int(sid)
        if s.get("role") not in ELIGIBLE_MENTOR_ROLES:
            continue
        prof = profiles.get(sid, {})
        if prof.get("available") is False:
            continue
        cap = int(prof.get("max_caseload") or MAX_DEFAULT_LOAD)
        load = _load(sid)
        if load >= cap:
            continue
        if sid in blocked:
            continue
        candidates.append((load, sid, s, prof))
    if prefer_roles:
        role_set = {str(r).strip().lower() for r in prefer_roles if r}
        narrowed = [row for row in candidates if str((row[2] or {}).get("role") or "").lower() in role_set]
        if narrowed:
            candidates = narrowed
    if prefer_staff_id is not None:
        try:
            preferred = int(prefer_staff_id)
        except (TypeError, ValueError):
            preferred = None
        if preferred is not None:
            for _load_n, sid, s, _prof in candidates:
                if sid == preferred:
                    return sid
            for s in staff:
                sid = s.get("staff_id")
                if sid is None:
                    continue
                sid = int(sid)
                if sid == preferred and s.get("role") in ELIGIBLE_MENTOR_ROLES and sid not in blocked:
                    return sid
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]))
    return candidates[0][1]


def _attendance_context(student_id):
    """Non-identifying band only — no course names, sections, or raw IDs."""
    from src.database.db import get_student_attendance
    logs = get_student_attendance(student_id) or []
    if not logs:
        return "Attendance history not yet sufficient for a band."
    present = sum(1 for x in logs if x.get("is_present"))
    rate = present / max(len(logs), 1)
    if rate >= 0.85:
        band = "Regular presence"
    elif rate >= 0.70:
        band = "Watch — presence slipping"
    else:
        band = "Concerning presence gaps"
    return band


def assign_mentorship(student_id, actor_role, actor_ref, goal=None, risk_band=None, session_state=None, prefer_staff_id=None, kind=None):
    """Counsellor/admin/student-request entry. Never returns mentor or student names."""
    if session_state and _demo(session_state):
        return None, "Demo Mode cannot write anonymous mentorships into production."
    if not installed():
        return None, "Mentorship schema is not installed. Run supabase/schema_mentorship.sql."
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return None, "Invalid student."
    if student_id < 0:
        return None, "Demo identities cannot be assigned."
    if get_student_public(student_id) is None:
        return None, "Student not found."
    from src.moderation.service import participation_allowed
    if not participation_allowed(student_id):
        return None, "This student cannot receive a new mentorship while their account is restricted, suspended, or banned."
    track = _normalize_kind(kind)
    existing = _open_for_student(student_id)
    same_kind = []
    for item in existing:
        row = _fetch(item.get("mentorship_id")) or item
        session_kind = _session_kind(row)
        if track and session_kind and session_kind != track:
            continue
        same_kind.append(row or item)
    if same_kind:
        mid = same_kind[0].get("mentorship_id")
        row = _fetch(mid) or same_kind[0]
        if prefer_staff_id is not None and row:
            try:
                if int(row.get("mentor_staff_id")) != int(prefer_staff_id):
                    service = "counselling" if track == "counsellor" else "mentoring" if track == "mentor" else "support"
                    return None, f"This student already has an open {service} chat with another staff member."
            except (TypeError, ValueError):
                pass
            view = faculty_view(mid, prefer_staff_id)
            if view:
                return view, "Private chat already open. Continue in Anonymous Mentorship."
        return student_view(mid, student_id), "This student already has an open anonymous mentorship."
    if track in ("mentor",):
        track = "mentor"
        prefer_roles = ("mentor", "faculty")
        default_goal = "Private mentoring session."
        student_title = "Mentor session opened"
        student_body = "Mentoring started with {alias}. Identities stay hidden."
        staff_title = "New mentoring student assigned"
        done_msg = "Anonymous mentoring started."
    elif track in ("counsellor", "counselor", "counselling", "counseling"):
        track = "counsellor"
        prefer_roles = ("counsellor",)
        default_goal = "Private counselling session."
        student_title = "Counselling session opened"
        student_body = "Counselling started with {alias}. Identities stay hidden."
        staff_title = "New counselling student assigned"
        done_msg = "Anonymous counselling started."
    else:
        prefer_roles = None
        default_goal = "Supportive check-in after early-warning signals."
        student_title = "Anonymous mentor assigned"
        student_body = "Counseling started with {alias}. Identities stay hidden for 7 days."
        staff_title = "New anonymous student assigned"
        done_msg = "Anonymous counseling started."
    mentor_id = _pick_mentor(student_id, prefer_staff_id=prefer_staff_id, prefer_roles=prefer_roles)
    if not mentor_id:
        return None, "No available mentor. Increase faculty capacity or mark a mentor available."
    now = _now()
    due = now + timedelta(days=CYCLE_DAYS)
    student_alias = _alias("STU")
    mentor_alias = _alias("MTR")
    row = store.insert("mentorships", {
        "student_id": student_id,
        "mentor_staff_id": mentor_id,
        "student_alias": student_alias,
        "mentor_alias": mentor_alias,
        "status": "ANONYMOUS_ACTIVE",
        "kind": track or None,
        "counseling_goal": goal or default_goal,
        "risk_band": risk_band or "Support",
        "attendance_context": _attendance_context(student_id),
        "started_at": now.isoformat(),
        "feedback_due_at": due.isoformat(),
    })
    if not row:
        last = ""
        try:
            last = str(store.last_error("mentorships") or "")
        except Exception:
            last = ""
        if "mentorships_one_open_per_student" in last or "duplicate key" in last.lower() or "unique" in last.lower():
            return None, (
                "This student already has another open support chat. Counselling and mentoring "
                "need separate open rows — apply the kind unique index in supabase/schema_mentorship.sql."
            )
        return None, "Could not create mentorship."
    mid = row[0]["mentorship_id"]
    store.insert("anonymous_profiles", {"alias": student_alias, "mentorship_id": mid, "party": "student"})
    store.insert("anonymous_profiles", {"alias": mentor_alias, "mentorship_id": mid, "party": "mentor"})
    store.insert("mentor_assignments", {
        "mentorship_id": mid,
        "student_id": student_id,
        "mentor_staff_id": mentor_id,
        "outcome": "assigned",
    })
    _notify(
        role="student", student_id=student_id, mentorship_id=mid,
        title=student_title,
        body=student_body.format(alias=mentor_alias),
    )
    _notify(
        role="mentor", staff_id=mentor_id, mentorship_id=mid,
        title=staff_title,
        body=f"You are matched with {student_alias}. You will not see their identity unless they accept after 7 days.",
    )
    _audit(actor_role, actor_ref, "assigned", mid, f"alias {student_alias}/{mentor_alias}")
    return student_view(mid, student_id), done_msg


def student_view(mentorship_id, student_id):
    row = _fetch(mentorship_id)
    if not row:
        return None
    if int(row["student_id"]) != int(student_id):
        _audit("student", student_id, "denied_cross_access", mentorship_id)
        return None
    payload = {
        "mentorshipId": row["mentorship_id"],
        "anonymousMentorId": row["mentor_alias"],
        "anonymousStudentId": row["student_alias"],
        "status": row["status"],
        "kind": _session_kind(row) or None,
        "counselingGoal": row.get("counseling_goal"),
        "startedAt": row.get("started_at"),
        "feedbackDueAt": row.get("feedback_due_at"),
        "daysRemaining": days_remaining(row),
        "identityReveal": row["status"] in REVEALED_STATUSES,
    }
    if row["status"] in REVEALED_STATUSES:
        staff = get_staff_public(row["mentor_staff_id"]) or {}
        payload["mentorName"] = staff.get("name")
        payload["mentorDesignation"] = staff.get("role")
        payload["mentorProfessional"] = "Authorized campus mentor on Classora."
        payload["statusLabel"] = "Mentorship Accepted — Identities Revealed"
    else:
        payload["statusLabel"] = {
            "ANONYMOUS_ACTIVE": "Anonymous counseling in progress",
            "FEEDBACK_PENDING": "Feedback unlocked — identities still hidden",
            "ASSIGNED": "Mentor assigned",
            "REJECTED": "Closed without identity reveal",
            "REASSIGNMENT_PENDING": "Reassignment in progress",
            "COMPLETED": "Completed",
            "SUSPENDED": "Suspended",
        }.get(row["status"], row["status"])
    return payload


def faculty_view(mentorship_id, staff_id):
    row = _fetch(mentorship_id)
    if not row:
        return None
    if int(row["mentor_staff_id"]) != int(staff_id):
        _audit("mentor", staff_id, "denied_cross_access", mentorship_id)
        return None
    payload = {
        "mentorshipId": row["mentorship_id"],
        "anonymousStudentId": row["student_alias"],
        "anonymousMentorId": row["mentor_alias"],
        "kind": _session_kind(row) or None,
        "riskLevel": row.get("risk_band") or "Support",
        "counselingGoal": row.get("counseling_goal"),
        "attendanceContext": row.get("attendance_context"),
        "mentorshipStartDate": row.get("started_at"),
        "feedbackDueAt": row.get("feedback_due_at"),
        "daysRemaining": days_remaining(row),
        "status": row["status"],
        "identityReveal": row["status"] in REVEALED_STATUSES,
    }
    if row["status"] in REVEALED_STATUSES:
        stu = get_student_public(row["student_id"]) or {}
        payload["studentName"] = stu.get("name")
        payload["studentRecordId"] = row["student_id"]
        payload["statusLabel"] = "Mentorship Accepted — Identities Revealed"
    else:
        payload["statusLabel"] = "Anonymous — student identity hidden"
    return payload


def list_for_student(student_id):
    if not installed():
        return []
    try:
        rows = supabase.table("mentorships").select("mentorship_id,status,created_at").eq(
            "student_id", student_id
        ).order("created_at", desc=True).execute().data or []
    except Exception:
        return []
    out = []
    for r in rows:
        view = student_view(r["mentorship_id"], student_id)
        if view:
            out.append(view)
    return out


def list_for_faculty(staff_id):
    if not installed():
        return []
    try:
        rows = supabase.table("mentorships").select("mentorship_id,status,created_at").eq(
            "mentor_staff_id", staff_id
        ).order("created_at", desc=True).execute().data or []
    except Exception:
        return []
    out = []
    for r in rows:
        view = faculty_view(r["mentorship_id"], staff_id)
        if view:
            out.append(view)
    return out


def messages(mentorship_id, *, student_id=None, staff_id=None):
    row = _authorize_party(mentorship_id, student_id=student_id, staff_id=staff_id)
    if not row:
        return []
    try:
        data = supabase.table("mentorship_messages").select("id,sender_role,body,created_at").eq(
            "mentorship_id", mentorship_id
        ).order("created_at").execute().data or []
    except Exception:
        return []
    return data


def post_message(mentorship_id, body, *, student_id=None, staff_id=None):
    row = _authorize_party(mentorship_id, student_id=student_id, staff_id=staff_id)
    if not row:
        return None, "Not authorized."
    if row["status"] in ("REJECTED", "COMPLETED", "SUSPENDED"):
        return None, "This mentorship is closed."
    from src.moderation.service import participation_allowed
    if not participation_allowed(row.get("student_id")):
        return None, "Counseling is paused because the student's account is restricted or banned."
    role = "student" if student_id is not None else "mentor"
    text = (body or "").strip()
    if not text:
        return None, "Message is empty."
    saved = store.insert("mentorship_messages", {
        "mentorship_id": mentorship_id,
        "sender_role": role,
        "body": text[:4000],
    })
    if not saved:
        try:
            saved = supabase.table("mentorship_messages").insert({
                "mentorship_id": mentorship_id,
                "sender_role": role,
                "body": text[:4000],
            }).execute().data
        except Exception as exc:
            return None, f"Could not save the message: {exc}"
    if not saved:
        return None, "Could not save the message. Confirm mentorship_messages exists in Supabase."
    return True, "Sent."


def add_session(mentorship_id, title, notes, *, student_id=None, staff_id=None):
    row = _authorize_party(mentorship_id, student_id=student_id, staff_id=staff_id)
    if not row:
        return None, "Not authorized."
    from src.moderation.service import participation_allowed
    if not participation_allowed(row.get("student_id")):
        return None, "Counseling is paused because the student's account is restricted or banned."
    role = "student" if student_id is not None else "mentor"
    store.insert("mentorship_sessions", {
        "mentorship_id": mentorship_id,
        "title": (title or "Session")[:120],
        "notes": (notes or "")[:2000],
        "created_by_role": role,
    })
    return True, "Session recorded."


def sessions(mentorship_id, *, student_id=None, staff_id=None):
    if not _authorize_party(mentorship_id, student_id=student_id, staff_id=staff_id):
        return []
    try:
        return supabase.table("mentorship_sessions").select("id,title,notes,created_by_role,created_at").eq(
            "mentorship_id", mentorship_id
        ).order("created_at", desc=True).execute().data or []
    except Exception:
        return []


def _authorize_party(mentorship_id, student_id=None, staff_id=None):
    row = _fetch(mentorship_id)
    if not row:
        return None
    if student_id is not None and int(row["student_id"]) == int(student_id):
        return row
    if staff_id is not None and int(row["mentor_staff_id"]) == int(staff_id):
        return row
    _audit("unknown", student_id or staff_id, "denied_party", mentorship_id)
    return None


def notifications_for(*, student_id=None, staff_id=None, role=None):
    if not installed():
        return []
    try:
        q = supabase.table("mentorship_notifications").select("id,title,body,created_at,read_at,mentorship_id").order(
            "created_at", desc=True
        ).limit(30)
        if student_id is not None:
            q = q.eq("recipient_student_id", student_id)
        elif staff_id is not None:
            q = q.eq("recipient_staff_id", staff_id)
        else:
            return []
        return q.execute().data or []
    except Exception:
        return []


def submit_feedback(mentorship_id, student_id, answers: dict, session_state=None):
    """Only the assigned student may submit. Reveal is server-side and idempotent."""
    if session_state and _demo(session_state):
        return None, "Demo Mode cannot submit production feedback."
    row = _fetch(mentorship_id)
    if not row:
        return None, "Mentorship not found."
    if int(row["student_id"]) != int(student_id):
        _audit("student", student_id, "denied_feedback", mentorship_id)
        return None, "Not authorized."
    if row["status"] in REVEALED_STATUSES:
        return student_view(mentorship_id, student_id), "Already accepted — identities remain revealed."
    if row["status"] != "FEEDBACK_PENDING":
        return None, "Feedback is only available after the 7-day anonymous period."
    continue_yes = bool(answers.get("want_to_continue"))
    existing = store.select("mentorship_feedback", mentorship_id=mentorship_id)
    if not existing:
        store.insert("mentorship_feedback", {
            "mentorship_id": mentorship_id,
            "student_id": student_id,
            "satisfaction": int(answers.get("satisfaction") or 3),
            "mentor_helpful": bool(answers.get("mentor_helpful")),
            "felt_comfortable": bool(answers.get("felt_comfortable")),
            "understood_concerns": bool(answers.get("understood_concerns")),
            "counseling_helped": bool(answers.get("counseling_helped")),
            "want_to_continue": continue_yes,
            "written_feedback": (answers.get("written_feedback") or "")[:2000],
        })
    _notify(
        role="student", student_id=student_id, mentorship_id=mentorship_id,
        title="Feedback submitted",
        body="Your anonymous review was recorded.",
    )
    _notify(
        role="mentor", staff_id=row["mentor_staff_id"], mentorship_id=mentorship_id,
        title="Student feedback received",
        body="A review was submitted. Identity is revealed only if the student accepted mentorship.",
    )
    if continue_yes:
        return _reveal(row, student_id)
    return _reject_and_reassign(row, student_id, session_state)


def _reveal(row, student_id):
    mid = row["mentorship_id"]
    if row["status"] in REVEALED_STATUSES:
        return student_view(mid, student_id), "Mentorship Accepted — Identities Revealed"
    _update(mid, {"status": "IDENTITIES_REVEALED", "revealed_at": _now().isoformat()})
    store.insert("identity_reveals", {
        "mentorship_id": mid,
        "revealed_by_student_id": student_id,
        "irreversible": True,
    })
    store.insert("mentor_assignments", {
        "mentorship_id": mid,
        "student_id": student_id,
        "mentor_staff_id": row["mentor_staff_id"],
        "outcome": "accepted",
    })
    _notify(
        role="student", student_id=student_id, mentorship_id=mid,
        title="Identities revealed",
        body="You chose to continue. You can now see your mentor's professional identity.",
    )
    _notify(
        role="mentor", staff_id=row["mentor_staff_id"], mentorship_id=mid,
        title="Mentorship accepted",
        body="The student accepted. Identities are now revealed for continued counseling.",
    )
    _audit("student", student_id, "identity_revealed", mid, "irreversible")
    return student_view(mid, student_id), "Mentorship Accepted — Identities Revealed"


def _reject_and_reassign(row, student_id, session_state):
    mid = row["mentorship_id"]
    _update(mid, {"status": "REJECTED", "closed_at": _now().isoformat()})
    store.insert("mentor_assignments", {
        "mentorship_id": mid,
        "student_id": student_id,
        "mentor_staff_id": row["mentor_staff_id"],
        "outcome": "rejected",
    })
    _notify(
        role="student", student_id=student_id, mentorship_id=mid,
        title="New mentor will be assigned",
        body="Your feedback has been recorded. We will assign you another mentor. Identities were not revealed.",
    )
    _notify(
        role="mentor", staff_id=row["mentor_staff_id"], mentorship_id=mid,
        title="Student reassigned",
        body=f"Anonymous student {row.get('student_alias')} will be matched with another mentor. Identity remains hidden.",
    )
    _audit("student", student_id, "rejected_no_reveal", mid)
    new_view, msg = assign_mentorship(
        student_id,
        "system",
        "reassign",
        goal=row.get("counseling_goal"),
        risk_band=row.get("risk_band"),
        session_state=session_state,
    )
    if new_view:
        _update(new_view["mentorshipId"], {"previous_mentorship_id": mid})
        return new_view, "Your feedback has been recorded. We will assign you another mentor."
    return student_view(mid, student_id), msg or "Your feedback has been recorded. We will assign you another mentor."


def request_reassignment(mentorship_id, student_id, session_state=None):
    row = _fetch(mentorship_id)
    if not row or int(row["student_id"]) != int(student_id):
        return None, "Not authorized."
    if row["status"] in REVEALED_STATUSES:
        return None, "Identities are already revealed. Ask an administrator to close the relationship."
    if row["status"] in ("REJECTED", "COMPLETED"):
        return None, "Already closed."
    return _reject_and_reassign(row, student_id, session_state)


def admin_overview():
    """Aggregates only — no names, no chat."""
    if not installed():
        return {"installed": False, "rows": [], "metrics": {}}
    try:
        rows = supabase.table("mentorships").select(
            "mentorship_id,student_alias,mentor_alias,status,started_at,feedback_due_at,revealed_at"
        ).order("created_at", desc=True).limit(200).execute().data or []
    except Exception:
        rows = []
    fb = store.select("mentorship_feedback") or []
    scores = [int(x["satisfaction"]) for x in fb if x.get("satisfaction") is not None]
    accepted = sum(1 for r in rows if r.get("status") in REVEALED_STATUSES)
    rejected = sum(1 for r in rows if r.get("status") == "REJECTED")
    decided = accepted + rejected
    metrics = {
        "total": len(rows),
        "acceptanceRate": round(100 * accepted / decided, 1) if decided else None,
        "reassignmentRate": round(100 * rejected / max(len(rows), 1), 1),
        "averageFeedback": round(sum(scores) / len(scores), 2) if scores else None,
        "identityReveals": accepted,
        "pendingFeedback": sum(1 for r in rows if r.get("status") == "FEEDBACK_PENDING"),
        "activeAnonymous": sum(1 for r in rows if r.get("status") == "ANONYMOUS_ACTIVE"),
    }
    return {"installed": True, "rows": rows, "metrics": metrics}


def close_chat(mentorship_id, *, student_id=None, staff_id=None):
    """End the private thread. Does not reveal names."""
    row = _authorize_party(mentorship_id, student_id=student_id, staff_id=staff_id)
    if not row:
        return None, "Not authorized."
    if row["status"] in ("REJECTED", "COMPLETED", "SUSPENDED"):
        return True, "This chat is already closed."
    _update(mentorship_id, {"status": "COMPLETED", "closed_at": _now().isoformat()})
    _notify(
        role="student", student_id=row.get("student_id"), mentorship_id=mentorship_id,
        title="Private chat closed",
        body="The anonymous counselling chat was closed. Identities stay hidden.",
    )
    _notify(
        role="mentor", staff_id=row.get("mentor_staff_id"), mentorship_id=mentorship_id,
        title="Private chat closed",
        body=f"The chat with {row.get('student_alias')} was closed. Identities stay hidden.",
    )
    _audit(
        "student" if student_id is not None else "mentor",
        student_id or staff_id,
        "closed_chat",
        mentorship_id,
    )
    return True, "Private chat closed. Identities stay hidden."


def admin_suspend(mentorship_id, actor_ref):
    row = _fetch(mentorship_id)
    if not row:
        return None, "Not found."
    if row["status"] in REVEALED_STATUSES:
        _update(mentorship_id, {"status": "COMPLETED", "closed_at": _now().isoformat()})
    else:
        _update(mentorship_id, {"status": "SUSPENDED", "closed_at": _now().isoformat()})
    _audit("administrator", actor_ref, "suspended", mentorship_id)
    return True, "Mentorship suspended."


def strip_identity(payload: dict) -> dict:
    if not payload:
        return payload
    return {k: v for k, v in payload.items() if k not in IDENTITY_KEYS}
