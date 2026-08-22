from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.api.deps import require_role, require_session
from src.api.serialize import clean
from src.database.auth_db import (
    activate_teacher_invite as cloud_activate,
    change_teacher_password as cloud_change_password,
    create_teacher_invite as cloud_invite,
    get_login_history,
    list_teacher_invites as cloud_list_invites,
    reset_teacher_password as cloud_reset,
)
from src.database.config import is_supabase_configured
from src.database import local_store as local
from src.database.institution import apply_filters, build_metrics, load_teacher_institution
from src.mentorship import service as mentorship
from src.moderation import policy as mod_policy
from src.moderation import service as moderation
from src.database.db import get_all_students
from src.success import store
from src.success.intelligence import library, load_bundle, logs_by_student, profile_map, student_360
from src.success.notify import for_recipient, notify
from src.success.ops import build_report, parse_import_csv, report_rows, search_profiles, settings_payload, utc_now
from src.success.risk_service import get_current_risk
from src.success.staff_auth import activate_staff, invite_staff, list_staff_invites
from src.success.twin import build_twin

router = APIRouter()


def _cloud():
    return is_supabase_configured()


def _actor(session: dict):
    if session.get("staff_data"):
        return session["staff_data"].get("username")
    if session.get("teacher_data"):
        return session["teacher_data"].get("username")
    if session.get("student_data"):
        return session["student_data"].get("name")
    return session.get("user_role")


def _must_save(rows, detail="Could not save. Check that the Success Hub tables exist in Supabase."):
    if not rows:
        raise HTTPException(status_code=500, detail=detail)
    return rows


def _support_role(session: dict) -> bool:
    return session.get("user_role") in ("counsellor", "administrator", "faculty", "mentor", "teacher")


def _modules(role: str) -> list[str]:
    options = []
    if role in ("teacher", "administrator", "counsellor"):
        options += [
            "Institution success", "Counsellor", "Student 360", "Early warning", "Recommender",
            "Human review", "Cases", "Outcomes", "Recovery", "What-if", "Digital Twin",
            "Explainable AI", "Predictive Twin", "Reports", "Search", "Import", "Monitoring",
            "Health", "Settings", "Assistant", "Notifications", "Communication", "Appointments",
            "Academic", "Attendance intel", "LMS",
        ]
    if role in ("faculty", "mentor"):
        options += ["Digital Twin", "Explainable AI", "Predictive Twin", "What-if", "Notifications"]
    if role == "administrator":
        options += ["Ecosystem analytics", "Mentorship admin", "Complaint Management"]
    if role in ("faculty", "mentor", "teacher"):
        options += ["Faculty portal"]
    if role in ("faculty", "mentor", "counsellor"):
        options += ["Anonymous Mentorship"]
    if role in ("faculty", "mentor", "counsellor", "teacher"):
        options += ["Report Student"]
    if role == "student":
        options = ["Student snapshot", "My Digital Twin", "My Risk", "AI Explanation", "Recovery AI",
                   "Future trajectory", "Interventions", "Notifications", "Ask for support",
                   "Anonymous Mentorship", "Account"]
    return list(dict.fromkeys(options))


def _alerts(profiles):
    resolved = set()
    for row in store.select("alerts") or []:
        if str(row.get("status") or "").lower() != "resolved":
            continue
        resolved.add((str(row.get("student_id") or ""), str(row.get("title") or "")))
    alerts = []
    for p in profiles:
        cat = (p.get("prediction") or {}).get("category")
        if cat in ("Critical", "High"):
            alerts.append({"student": p.get("name"), "student_id": p.get("student_id"), "severity": cat, "source": "risk-model", "title": f"Predicted {cat} risk"})
        if (p.get("attendance") or {}).get("consecutive_absences", 0) >= 3:
            alerts.append({"student": p.get("name"), "student_id": p.get("student_id"), "severity": "High", "source": "attendance", "title": "Consecutive absences"})
    seen, uniq = set(), []
    for a in alerts:
        key = (a.get("student"), a.get("title"))
        persist = (str(a.get("student_id") or ""), str(a.get("title") or ""))
        if key in seen or persist in resolved:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq


def _hub_settings():
    rows = store.select("institution_settings") or []
    if not rows:
        return {"institution_name": "", "support_note": ""}
    return settings_payload(rows[0].get("settings"))


def _known_student_ids():
    try:
        rows = get_all_students("student_id") or []
        return {int(r["student_id"]) for r in rows if r.get("student_id") is not None}
    except Exception:
        return set()


def _ops_role(session: dict) -> bool:
    return session.get("user_role") in ("teacher", "administrator", "counsellor")


def _duplicate_import_row(table, row, existing):
    sid = str(row.get("student_id"))
    if table == "lms_events":
        return any(
            str(item.get("student_id")) == sid
            and str(item.get("event_type") or "") == str(row.get("event_type") or "")
            and str(item.get("course_code") or "") == str(row.get("course_code") or "")
            for item in existing or []
        )
    return any(
        str(item.get("student_id")) == sid
        and str(item.get("assessment") or "") == str(row.get("assessment") or "")
        and str(item.get("score") or "") == str(row.get("score") or "")
        for item in existing or []
    )


class PasswordChangeIn(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class PasswordResetIn(BaseModel):
    username: str
    registered_name: str
    new_password: str
    confirm_password: str


class InviteIn(BaseModel):
    invited_name: str
    invited_username: str


class StaffInviteIn(BaseModel):
    invited_name: str
    invited_username: str
    role: str = "counsellor"


class ActivateIn(BaseModel):
    username: str
    token: str
    password: str
    confirm_password: str


class HelpIn(BaseModel):
    message: str = "Help request"


class HelpAckIn(BaseModel):
    message_id: int


class AppointmentIn(BaseModel):
    kind: str = "counsellor"
    starts_at: str | None = None


class AppointmentConnectIn(BaseModel):
    appointment_id: int


class RecommendIn(BaseModel):
    student_id: int


class CaseIn(BaseModel):
    student_id: int
    intervention_name: str
    notes: str = ""
    priority: str = "medium"


class OutcomeIn(BaseModel):
    student_id: int
    result: str
    notes: str = ""


class AssistantIn(BaseModel):
    question: str


class MentorshipAssignIn(BaseModel):
    student_id: int
    goal: str | None = None


class MessageIn(BaseModel):
    body: str


class SessionIn(BaseModel):
    title: str
    notes: str = ""


class FeedbackIn(BaseModel):
    answers: dict = Field(default_factory=dict)


class ComplaintIn(BaseModel):
    student_reference: str
    category: str
    severity: str = "medium"
    description: str
    requested_action: str = "review"


class AppealIn(BaseModel):
    reason: str
    explanation: str
    complaint_id: int | None = None


class AppealReviewIn(BaseModel):
    appeal_id: int
    decision: str
    notes: str = ""
    duration_hours: int | None = None


class DecideIn(BaseModel):
    action: str
    notes: str = ""


class SettingsIn(BaseModel):
    institution_name: str = ""
    support_note: str = ""


class TaskIn(BaseModel):
    student_id: int
    task: str


class TaskDoneIn(BaseModel):
    task_id: int
    done: bool = True


class AlertResolveIn(BaseModel):
    alert_id: int | None = None
    student_id: int | None = None
    title: str = ""
    severity: str = "High"
    source: str = "risk-model"


@router.post("/api/auth/teacher/forgot")
def teacher_forgot(body: PasswordResetIn):
    if _cloud():
        ok, msg = cloud_reset(body.username, body.registered_name, body.new_password, body.confirm_password)
    else:
        ok, msg = local.reset_teacher_password(body.username, body.registered_name, body.new_password, body.confirm_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/auth/teacher/activate")
def teacher_activate(body: ActivateIn):
    if _cloud():
        ok, msg = cloud_activate(body.username, body.token, body.password, body.confirm_password)
    else:
        ok, msg = local.activate_teacher_invite(body.username, body.token, body.password, body.confirm_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/auth/staff/activate")
def staff_activate(body: ActivateIn):
    staff, msg = activate_staff(body.username, body.token, body.password, body.confirm_password)
    if not staff:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/teacher/password")
def teacher_password(body: PasswordChangeIn, session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        ok, msg = cloud_change_password(teacher_id, body.current_password, body.new_password, body.confirm_password)
    else:
        ok, msg = local.change_teacher_password(teacher_id, body.current_password, body.new_password, body.confirm_password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/teacher/invites")
def teacher_invite(body: InviteIn, session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        token, msg = cloud_invite(body.invited_name, body.invited_username, teacher_id)
    else:
        token, msg = local.create_teacher_invite(body.invited_name, body.invited_username, teacher_id)
    if not token:
        raise HTTPException(status_code=400, detail=msg)
    return {"token": token, "detail": msg}


@router.get("/api/teacher/invites")
def teacher_invites(session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    rows = cloud_list_invites(teacher_id) if _cloud() else local.list_teacher_invites(teacher_id)
    return clean(rows)


@router.get("/api/teacher/login-history")
def teacher_history(session: dict = Depends(require_role("teacher"))):
    return clean(get_login_history(limit=40))


@router.get("/api/teacher/share/{subject_code}")
def share_subject(subject_code: str, session: dict = Depends(require_role("teacher"))):
    return {
        "subject_code": subject_code,
        "join_url": f"/app?join-code={subject_code}",
        "message": f"Share this code with students: {subject_code}",
    }


@router.get("/api/success/workspace")
def success_workspace(session: dict = Depends(require_session)):
    role = session.get("user_role")
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    student_id = (session.get("student_data") or {}).get("student_id")
    staff = session.get("staff_data") or {}
    if role == "student" and student_id is not None:
        bundle = load_bundle(session, student_id=student_id)
        profiles = profile_map(bundle)
        mine = profiles[0] if profiles else None
        twins = {}
        if mine:
            twins[str(mine["student_id"])] = build_twin(
                mine,
                logs=logs_by_student(bundle).get(mine["student_id"]),
                role="student",
                lite=True,
            )
        notes = []
        m_rows = []
        try:
            mentorship.tick_lifecycle(session)
            notes = list(for_recipient(role="student", recipient_id=student_id) or [])
            notes += mentorship.notifications_for(student_id=student_id) or []
            m_rows = mentorship.list_for_student(student_id) or []
        except Exception:
            notes = notes or []
            m_rows = m_rows or []
        snap = None
        try:
            snap = moderation.student_snapshot(student_id)
        except Exception:
            snap = None
        appeals = []
        try:
            appeals = moderation.student_appeals(student_id) or []
        except Exception:
            appeals = []
        student_name = (session.get("student_data") or {}).get("name")
        try:
            sid = int(student_id)
        except (TypeError, ValueError):
            sid = student_id
        own_cases = [
            row for row in (store.select("intervention_cases") or [])
            if str(row.get("student_id")) == str(sid)
        ]
        own_messages = [
            row for row in (store.select("messages") or [])
            if row.get("sender") == student_name
        ]
        own_outcomes = []
        case_ids = {row.get("id") for row in own_cases}
        for row in store.select("intervention_outcomes") or []:
            if row.get("case_id") in case_ids:
                own_outcomes.append(row)
        academic = store.select("academic_records", student_id=sid) or []
        lms = store.select("lms_events", student_id=sid) or []
        appointments = store.select("appointments", student_id=sid) or []
        tasks = store.select("recovery_tasks", student_id=sid) or []
        alerts = _alerts(profiles)
        return clean({
            "role": role,
            "actor": _actor(session),
            "demo": False,
            "modules": _modules(role),
            "profiles": profiles,
            "twins": twins,
            "mine": mine,
            "risk": None,
            "cases": own_cases,
            "recommendations": (mine or {}).get("recommendations") or [],
            "academic": academic,
            "lms": lms,
            "alerts": alerts,
            "library": library(),
            "notifications": notes[:30],
            "appointments": appointments,
            "tasks": tasks,
            "messages": own_messages,
            "outcomes": own_outcomes,
            "institution": None,
            "mentorship": m_rows,
            "mentorship_admin": None,
            "complaints": [],
            "appeals": appeals,
            "account": snap,
            "settings": _hub_settings(),
            "report": build_report(profiles, own_cases, alerts, appointments, academic, lms, own_outcomes),
            "import_jobs": [],
            "staff_invites": [],
            "stored_alerts": [],
            "moderation_meta": {
                "categories": list(mod_policy.CATEGORIES),
                "severities": list(mod_policy.SEVERITIES),
                "actions": list(mod_policy.REQUESTED_ACTIONS.values()) if isinstance(mod_policy.REQUESTED_ACTIONS, dict) else list(mod_policy.REQUESTED_ACTIONS),
                "execute_actions": list(mod_policy.EXECUTE_ACTIONS),
            },
            "disclaimer": "Predicted risk is a support signal, not a diagnosis.",
        })
    bundle = load_bundle(
        session,
        teacher_id=teacher_id if role != "student" else None,
        student_id=student_id if role == "student" else None,
    )
    profiles = profile_map(bundle)
    twins = {}
    twin_rows = profiles[:1] if role == "student" else profiles[:20]
    for profile in twin_rows:
        twins[str(profile["student_id"])] = build_twin(profile, logs=logs_by_student(bundle).get(profile["student_id"]), role="student" if role == "student" else "staff")
    mine = profiles[0] if role == "student" and profiles else None
    risk = None
    if student_id is not None and role != "student":
        mine = student_360(bundle, student_id)
        risk = get_current_risk(student_id, session_state=session, actor_role="student", actor_student_id=student_id)
        if mine:
            twins[str(student_id)] = build_twin(mine, logs=logs_by_student(bundle).get(student_id), role="student")
    elif student_id is not None and mine:
        twins[str(student_id)] = twins.get(str(student_id)) or build_twin(mine, logs=logs_by_student(bundle).get(student_id), role="student")
    notes = []
    try:
        if student_id is not None:
            notes = list(for_recipient(role="student", recipient_id=student_id) or [])
            notes += mentorship.notifications_for(student_id=student_id) or []
        elif staff.get("staff_id") is not None:
            notes = list(for_recipient(role=role, recipient_id=staff.get("staff_id")) or [])
            notes += mentorship.notifications_for(staff_id=staff.get("staff_id"), role=role) or []
    except Exception:
        notes = []
    inst = None
    if role == "teacher" and teacher_id is not None:
        try:
            bundle_i = load_teacher_institution(teacher_id)
            inst = build_metrics(apply_filters(bundle_i))
        except Exception:
            inst = None
    m_rows = []
    try:
        m_rows = mentorship.list_for_student(student_id) if student_id is not None else []
        if staff.get("staff_id") is not None:
            m_rows = mentorship.list_for_faculty(staff["staff_id"])
    except Exception:
        m_rows = []
    complaints = []
    try:
        if role == "administrator":
            complaints = moderation.list_admin_complaints()
        elif role in ("faculty", "mentor", "counsellor", "teacher"):
            complaints = moderation.list_faculty_complaints(
                reporter_staff_id=staff.get("staff_id"),
                teacher_id=teacher_id,
            )
    except Exception:
        complaints = []
    snap = None
    try:
        snap = moderation.student_snapshot(student_id) if student_id is not None else None
    except Exception:
        snap = None
    try:
        appeals = moderation.list_appeals() if role == "administrator" else (moderation.student_appeals(student_id) if student_id is not None else [])
    except Exception:
        appeals = []
    try:
        admin_m = mentorship.admin_overview() if role == "administrator" else None
    except Exception:
        admin_m = None
    academic = bundle.get("academic") or []
    lms = bundle.get("lms") or []
    cases = bundle.get("cases") or []
    appointments = store.select("appointments", **({"student_id": student_id} if student_id is not None else {})) or []
    tasks = store.select("recovery_tasks", **({"student_id": student_id} if student_id is not None else {})) or []
    outcomes = store.select("intervention_outcomes") or []
    stored_alerts = store.select("alerts") or [] if role != "student" else []
    if role == "teacher":
        allowed = {str(p.get("student_id")) for p in profiles}
        appointments = [row for row in appointments if str(row.get("student_id")) in allowed]
        tasks = [row for row in tasks if str(row.get("student_id")) in allowed]
        stored_alerts = [row for row in stored_alerts if str(row.get("student_id")) in allowed]
        case_ids = {row.get("id") for row in cases}
        outcomes = [
            row for row in outcomes
            if str(row.get("student_id")) in allowed or row.get("case_id") in case_ids
        ]
    alerts = _alerts(profiles)
    settings = _hub_settings()
    invites = list_staff_invites() if role == "administrator" else []
    jobs = store.select("import_jobs") or [] if role != "student" else []
    return clean({
        "role": role,
        "actor": _actor(session),
        "demo": bool(bundle.get("demo") or session.get("demo_mode")),
        "modules": _modules(role),
        "profiles": profiles,
        "twins": twins,
        "mine": mine,
        "risk": risk,
        "cases": cases,
        "recommendations": bundle.get("recommendations") or [],
        "academic": academic,
        "lms": lms,
        "alerts": alerts,
        "library": library(),
        "notifications": notes[:30],
        "appointments": appointments,
        "tasks": tasks,
        "messages": store.select("messages") if role != "student" else [],
        "outcomes": outcomes,
        "institution": inst,
        "mentorship": m_rows,
        "mentorship_admin": admin_m,
        "complaints": complaints,
        "appeals": appeals,
        "account": snap,
        "settings": settings,
        "report": build_report(profiles, cases, alerts, appointments, academic, lms, outcomes),
        "import_jobs": jobs,
        "staff_invites": invites,
        "stored_alerts": stored_alerts,
        "moderation_meta": {
            "categories": list(mod_policy.CATEGORIES),
            "severities": list(mod_policy.SEVERITIES),
            "actions": list(mod_policy.REQUESTED_ACTIONS.values()) if isinstance(mod_policy.REQUESTED_ACTIONS, dict) else list(mod_policy.REQUESTED_ACTIONS),
            "execute_actions": list(mod_policy.EXECUTE_ACTIONS),
        },
        "disclaimer": "Predicted risk is a support signal, not a diagnosis.",
    })


@router.post("/api/success/help")
def success_help(body: HelpIn, session: dict = Depends(require_role("student"))):
    student = session["student_data"]
    text = (body.message or "").strip() or "Help request"
    saved = store.insert("messages", {
        "sender": student.get("name"),
        "recipient": "counsellor",
        "channel": "in_app",
        "body": text,
        "status": "queued",
    })
    _must_save(saved, "Could not queue the help request.")
    notify(
        role="counsellor",
        recipient_id="caseload",
        title="New help request",
        body=f"{student.get('name') or 'A student'} asked for support. Open Communication.",
    )
    notify(
        role="student",
        recipient_id=student.get("student_id"),
        title="Help request sent",
        body="Support staff can see your request under Communication.",
    )
    return {"ok": True, "detail": "Request queued for support staff."}


@router.post("/api/success/help/ack")
def success_help_ack(body: HelpAckIn, session: dict = Depends(require_session)):
    if not _support_role(session):
        raise HTTPException(status_code=403, detail="Only support staff can acknowledge help requests.")
    updated = store.update("messages", {"id": body.message_id}, {"status": "seen"})
    if not updated:
        raise HTTPException(status_code=404, detail="Help request not found.")
    return {"ok": True, "detail": "Marked as seen."}


@router.post("/api/success/appointment")
def success_appointment(body: AppointmentIn, session: dict = Depends(require_role("student"))):
    student = session["student_data"]
    saved = store.insert("appointments", {
        "student_id": student["student_id"],
        "staff_name": body.kind,
        "kind": body.kind,
        "starts_at": body.starts_at or datetime.now().isoformat(timespec="minutes"),
        "status": "requested",
    })
    _must_save(saved, "Could not save the appointment request.")
    notify(
        role="counsellor",
        recipient_id="caseload",
        title="Counsellor meeting requested",
        body=f"Student ID {student.get('student_id')} requested a meeting. Open Appointments to connect privately.",
    )
    return {"ok": True, "detail": "Appointment requested. Wait for the counsellor to open a private chat."}


@router.post("/api/success/appointment/connect")
def success_appointment_connect(body: AppointmentConnectIn, session: dict = Depends(require_session)):
    """Counsellor accepts a named request by opening alias-only mentorship chat."""
    role = session.get("user_role")
    if role not in ("counsellor", "administrator", "mentor", "faculty"):
        raise HTTPException(status_code=403, detail="Only support staff can open the private chat.")
    staff_id = (session.get("staff_data") or {}).get("staff_id")
    if not staff_id:
        raise HTTPException(status_code=400, detail="Staff profile missing.")
    rows = store.select("appointments", id=body.appointment_id) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Appointment not found.")
    appt = rows[0]
    try:
        student_id = int(appt.get("student_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Appointment is missing a student.")
    prefer = staff_id if role != "administrator" else None
    row, msg = mentorship.assign_mentorship(
        student_id,
        role,
        staff_id,
        goal="Private counsellor chat after student request.",
        session_state=session,
        prefer_staff_id=prefer,
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    view = row
    if role != "student":
        view = mentorship.faculty_view(row.get("mentorshipId"), staff_id) or row
    store.update("appointments", {"id": body.appointment_id}, {
        "status": "connected",
        "notes": "Private alias chat opened in Anonymous Mentorship.",
    })
    return {
        "ok": True,
        "detail": msg or "Private chat opened. Continue in Anonymous Mentorship. Messages use aliases only.",
        "mentorship": clean(view),
        "student_alias": (view or {}).get("anonymousStudentId"),
        "mentor_alias": (view or {}).get("anonymousMentorId"),
    }


@router.post("/api/success/recommend")
def success_recommend(body: RecommendIn, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff submit recommendations for human review.")
    bundle = load_bundle(session, teacher_id=(session.get("teacher_data") or {}).get("teacher_id"))
    profile = student_360(bundle, body.student_id)
    recs = (profile or {}).get("recommendations") or []
    if not recs:
        raise HTTPException(status_code=400, detail="No recommendation to submit.")
    rec = recs[0]
    saved = store.insert("intervention_recommendations", {
        "student_id": body.student_id,
        "recommendation": rec.get("name"),
        "reason": rec.get("reason"),
        "confidence": rec.get("confidence"),
        "status": "pending",
    })
    _must_save(saved, "Could not queue the recommendation.")
    notify(
        role="counsellor",
        recipient_id="caseload",
        title="Recommendation pending review",
        body=f"Student ID {body.student_id}: {rec.get('name')}. Open Human review.",
    )
    return {"ok": True, "detail": "Queued for counsellor review."}


@router.post("/api/success/case")
def success_case(body: CaseIn, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff open intervention cases.")
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    saved = store.insert("intervention_cases", {
        "case_code": f"CASE-{body.student_id}-{stamp}-{uuid.uuid4().hex[:4].upper()}",
        "student_id": body.student_id,
        "owner": _actor(session),
        "priority": body.priority,
        "status": "open",
        "intervention_name": body.intervention_name,
        "notes": body.notes,
        "deadline": datetime.now().isoformat(),
    })
    _must_save(saved, "Could not create the case.")
    pending = store.select("intervention_recommendations", student_id=body.student_id) or []
    for row in pending:
        if str(row.get("status") or "").lower() != "pending":
            continue
        store.update("intervention_recommendations", {"id": row["id"]}, {
            "status": "accepted",
            "reviewer": _actor(session),
        })
    return {"ok": True, "detail": "Case opened."}


@router.post("/api/success/outcome")
def success_outcome(body: OutcomeIn, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff record intervention outcomes.")
    cases = store.select("intervention_cases", student_id=body.student_id) or []
    open_cases = [row for row in cases if str(row.get("status") or "open").lower() == "open"]
    chosen = (open_cases or cases)
    case_id = chosen[-1].get("id") if chosen else None
    payload = {
        "classification": body.result or "improved",
        "notes": body.notes,
        "recorded_by": _actor(session),
    }
    if case_id is not None:
        payload["case_id"] = case_id
    saved = store.insert("intervention_outcomes", payload)
    _must_save(saved, "Could not record the outcome.")
    if case_id is not None:
        store.update("intervention_cases", {"id": case_id}, {
            "status": "closed",
            "closed_at": datetime.now().isoformat(),
            "closure_reason": body.result or "improved",
        })
    return {"ok": True, "detail": "Outcome recorded."}


@router.post("/api/success/assistant")
def success_assistant(body: AssistantIn, session: dict = Depends(require_session)):
    q = (body.question or "").lower()
    student_id = (session.get("student_data") or {}).get("student_id")
    rate = None
    if student_id is not None:
        bundle = load_bundle(session)
        p = student_360(bundle, student_id) or {}
        rate = (p.get("attendance") or {}).get("rate")
    if "attendance" in q:
        answer = f"Your recorded attendance is {rate if rate is not None else 'not available yet'}%."
    elif any(w in q for w in ("counsellor", "contact", "help")):
        answer = "Use Ask for support. Counsellors see those requests in Communication."
    elif any(w in q for w in ("plan", "task")):
        answer = "Your tasks are listed under Interventions."
    elif any(w in q for w in ("risk", "twin")):
        answer = "Open My Digital Twin and My Risk. Those figures come from recorded attendance and academics only."
    else:
        answer = "I can only answer from your attendance, Digital Twin, and assigned tasks."
    return {"answer": answer}


@router.post("/api/staff/invite")
def staff_invite(body: StaffInviteIn, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    token, msg = invite_staff(body.invited_name, body.invited_username, body.role, session["staff_data"].get("staff_id"))
    if not token:
        raise HTTPException(status_code=400, detail=msg)
    return {"token": token, "detail": msg}


@router.get("/api/staff/invites")
def staff_invites(session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    return {"invites": clean(list_staff_invites())}


@router.get("/api/success/search")
def success_search(q: str = "", session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff search the student directory.")
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    bundle = load_bundle(session, teacher_id=teacher_id)
    profiles = search_profiles(profile_map(bundle), q)
    return {"ok": True, "query": q, "count": len(profiles), "results": clean(report_rows(profiles))}


@router.get("/api/success/report")
def success_report(session: dict = Depends(require_session)):
    if not _ops_role(session) and session.get("user_role") not in ("faculty", "mentor"):
        raise HTTPException(status_code=403, detail="Staff only.")
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    bundle = load_bundle(session, teacher_id=teacher_id)
    profiles = profile_map(bundle)
    cases = bundle.get("cases") or []
    appointments = store.select("appointments") or []
    academic = bundle.get("academic") or []
    lms = bundle.get("lms") or []
    outcomes = store.select("intervention_outcomes") or []
    alerts = _alerts(profiles)
    report = build_report(profiles, cases, alerts, appointments, academic, lms, outcomes)
    return {"ok": True, "report": report, "rows": clean(report_rows(profiles))}


@router.get("/api/success/settings")
def success_settings_get(session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff only.")
    return {"ok": True, "settings": _hub_settings()}


@router.post("/api/success/settings")
def success_settings_save(body: SettingsIn, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    payload = settings_payload({"institution_name": body.institution_name, "support_note": body.support_note})
    existing = store.select("institution_settings", id=1) or store.select("institution_settings") or []
    if existing:
        rid = existing[0].get("id") if existing[0].get("id") is not None else 1
        updated = store.update("institution_settings", {"id": rid}, {"settings": payload})
        if not updated:
            raise HTTPException(status_code=500, detail="Could not save institution settings.")
    else:
        _must_save(store.insert("institution_settings", {"id": 1, "settings": payload}), "Could not save institution settings.")
    return {"ok": True, "detail": "Settings saved.", "settings": payload}


@router.post("/api/success/import")
async def success_import(
    kind: str = Form("academic"),
    file: UploadFile = File(...),
    session: dict = Depends(require_session),
):
    if not _ops_role(session):
        raise HTTPException(status_code=403, detail="Teachers, counsellors, and administrators can import records.")
    raw = (await file.read() or b"").decode("utf-8", errors="replace")
    rows, err = parse_import_csv(raw, kind)
    filename = file.filename or "upload.csv"
    if err:
        store.insert("import_jobs", {"kind": kind, "filename": filename, "status": "failed", "summary": err})
        raise HTTPException(status_code=400, detail=err)
    known = _known_student_ids()
    table = "lms_events" if str(kind).lower() in ("lms", "engagement") else "academic_records"
    existing = store.select(table) or []
    saved = 0
    skipped = []
    for row in rows:
        if known and int(row["student_id"]) not in known:
            skipped.append(f"{row['student_id']} unknown")
            continue
        if _duplicate_import_row(table, row, existing):
            skipped.append(f"{row['student_id']} duplicate")
            continue
        inserted = store.insert(table, row)
        if inserted:
            saved += 1
            if isinstance(inserted, list):
                existing.extend(inserted)
            else:
                existing.append(row)
        else:
            skipped.append(f"{row['student_id']} not saved")
    if saved == 0:
        summary = "No rows saved." + (f" {', '.join(skipped[:8])}." if skipped else "")
        store.insert("import_jobs", {"kind": kind, "filename": filename, "status": "failed", "summary": summary})
        raise HTTPException(status_code=400, detail=summary)
    status = "done" if not skipped else "partial"
    summary = f"{saved} row(s) imported into {table}."
    if skipped:
        summary += f" Skipped {len(skipped)}: {', '.join(skipped[:8])}."
    job = store.insert("import_jobs", {"kind": kind, "filename": filename, "status": status, "summary": summary})
    _must_save(job, "Imported records but could not write the import job log.")
    return {"ok": True, "detail": summary, "saved": saved, "skipped": skipped, "status": status}


@router.post("/api/success/task")
def success_task_create(body: TaskIn, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff assign recovery tasks.")
    text = (body.task or "").strip()
    if len(text) < 3:
        raise HTTPException(status_code=400, detail="Enter a task description.")
    known = _known_student_ids()
    if known and int(body.student_id) not in known:
        raise HTTPException(status_code=404, detail="Student not found.")
    saved = store.insert("recovery_tasks", {
        "student_id": body.student_id,
        "task": text,
        "done": False,
    })
    _must_save(saved, "Could not save the recovery task.")
    notify(
        role="student",
        recipient_id=body.student_id,
        title="New recovery task",
        body=text,
    )
    return {"ok": True, "detail": "Task assigned."}


@router.post("/api/success/task/done")
def success_task_done(body: TaskDoneIn, session: dict = Depends(require_session)):
    rows = store.select("recovery_tasks", id=body.task_id) or []
    if not rows:
        raise HTTPException(status_code=404, detail="Task not found.")
    task = rows[0]
    if session.get("user_role") == "student":
        sid = (session.get("student_data") or {}).get("student_id")
        if str(task.get("student_id")) != str(sid):
            raise HTTPException(status_code=403, detail="You can only update your own tasks.")
    updated = store.update("recovery_tasks", {"id": body.task_id}, {"done": bool(body.done)})
    if not updated:
        raise HTTPException(status_code=500, detail="Could not update the task.")
    return {"ok": True, "detail": "Task updated.", "done": bool(body.done)}


@router.post("/api/success/alert/resolve")
def success_alert_resolve(body: AlertResolveIn, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff resolve alerts.")
    now = utc_now()
    title = (body.title or "").strip()
    if body.alert_id is not None:
        rows = store.select("alerts", id=body.alert_id) or []
        if not rows:
            raise HTTPException(status_code=404, detail="Alert not found.")
        if str(rows[0].get("status") or "").lower() == "resolved":
            return {"ok": True, "detail": "Alert is already resolved."}
        updated = store.update("alerts", {"id": body.alert_id}, {
            "status": "resolved",
            "resolved_at": now,
            "owner": _actor(session),
        })
        if not updated:
            raise HTTPException(status_code=500, detail="Could not resolve the alert.")
        return {"ok": True, "detail": "Alert resolved."}
    if not title:
        raise HTTPException(status_code=400, detail="Alert title is required.")
    existing = [
        row for row in (store.select("alerts") or [])
        if str(row.get("student_id") or "") == str(body.student_id or "")
        and str(row.get("title") or "") == title
    ]
    open_rows = [row for row in existing if str(row.get("status") or "").lower() != "resolved"]
    if open_rows:
        store.update("alerts", {"id": open_rows[-1]["id"]}, {
            "status": "resolved",
            "resolved_at": now,
            "owner": _actor(session),
        })
        return {"ok": True, "detail": "Alert resolved."}
    if existing:
        return {"ok": True, "detail": "Alert is already resolved."}
    saved = store.insert("alerts", {
        "student_id": body.student_id,
        "source": body.source or "risk-model",
        "severity": body.severity or "High",
        "title": title,
        "status": "resolved",
        "owner": _actor(session),
        "resolved_at": now,
    })
    _must_save(saved, "Could not record the resolved alert.")
    return {"ok": True, "detail": "Alert marked resolved."}


@router.get("/api/mentorship")
def mentorship_list(session: dict = Depends(require_session)):
    mentorship.tick_lifecycle(session)
    if session.get("user_role") == "student":
        return clean(mentorship.list_for_student(session["student_data"]["student_id"]))
    staff_id = (session.get("staff_data") or {}).get("staff_id")
    if session.get("user_role") == "administrator":
        return clean(mentorship.admin_overview())
    return clean(mentorship.list_for_faculty(staff_id))


@router.post("/api/mentorship/assign")
def mentorship_assign(body: MentorshipAssignIn, session: dict = Depends(require_session)):
    actor = session.get("user_role")
    if actor == "student":
        own = (session.get("student_data") or {}).get("student_id")
        try:
            if int(body.student_id) != int(own):
                raise HTTPException(status_code=403, detail="You can only request mentorship for your own account.")
        except (TypeError, ValueError):
            raise HTTPException(status_code=403, detail="You can only request mentorship for your own account.")
    ref = (session.get("staff_data") or {}).get("staff_id") or (session.get("student_data") or {}).get("student_id")
    prefer = ref if actor in ("counsellor", "mentor", "faculty") else None
    row, msg = mentorship.assign_mentorship(
        body.student_id, actor, ref, goal=body.goal, session_state=session, prefer_staff_id=prefer
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg, "mentorship": clean(row)}


@router.get("/api/mentorship/{mentorship_id}")
def mentorship_one(mentorship_id: str, session: dict = Depends(require_session)):
    if session.get("user_role") == "student":
        return clean(mentorship.student_view(mentorship_id, session["student_data"]["student_id"]))
    return clean(mentorship.faculty_view(mentorship_id, (session.get("staff_data") or {}).get("staff_id")))


@router.get("/api/mentorship/{mentorship_id}/messages")
def mentorship_messages(mentorship_id: str, session: dict = Depends(require_session)):
    kwargs = {}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    return {"messages": clean(mentorship.messages(mentorship_id, **kwargs))}


@router.post("/api/mentorship/{mentorship_id}/messages")
def mentorship_post(mentorship_id: str, body: MessageIn, session: dict = Depends(require_session)):
    kwargs = {"body": body.body}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    ok, msg = mentorship.post_message(mentorship_id, **kwargs)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    thread = []
    if session.get("user_role") == "student":
        thread = mentorship.messages(mentorship_id, student_id=kwargs["student_id"])
    else:
        thread = mentorship.messages(mentorship_id, staff_id=kwargs["staff_id"])
    return {"ok": True, "detail": msg, "messages": clean(thread)}


@router.post("/api/mentorship/{mentorship_id}/sessions")
def mentorship_session(mentorship_id: str, body: SessionIn, session: dict = Depends(require_session)):
    kwargs = {"title": body.title, "notes": body.notes}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    ok, msg = mentorship.add_session(mentorship_id, **kwargs)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/mentorship/{mentorship_id}/feedback")
def mentorship_feedback(mentorship_id: str, body: FeedbackIn, session: dict = Depends(require_role("student"))):
    row, msg = mentorship.submit_feedback(mentorship_id, session["student_data"]["student_id"], body.answers, session_state=session)
    if row is None and msg:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg, "mentorship": clean(row)}


@router.post("/api/mentorship/{mentorship_id}/reassign")
def mentorship_reassign(mentorship_id: str, session: dict = Depends(require_role("student"))):
    row, msg = mentorship.request_reassignment(mentorship_id, session["student_data"]["student_id"], session_state=session)
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/mentorship/{mentorship_id}/close")
def mentorship_close(mentorship_id: str, session: dict = Depends(require_session)):
    kwargs = {}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    ok, msg = mentorship.close_chat(mentorship_id, **kwargs)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/mentorship/{mentorship_id}/suspend")
def mentorship_suspend(mentorship_id: str, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    return clean(mentorship.admin_suspend(mentorship_id, session["staff_data"].get("staff_id")))


@router.post("/api/moderation/complaints")
def create_complaint(body: ComplaintIn, session: dict = Depends(require_session)):
    role = session.get("user_role")
    row, msg = moderation.create_complaint(
        reporter_role=role,
        reporter_staff_id=(session.get("staff_data") or {}).get("staff_id"),
        teacher_id=(session.get("teacher_data") or {}).get("teacher_id"),
        student_reference=body.student_reference,
        category=body.category,
        severity=body.severity,
        description=body.description,
        requested_action=body.requested_action,
        session_state=session,
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg, "complaint": clean(row)}


@router.post("/api/moderation/appeals")
def create_appeal(body: AppealIn, session: dict = Depends(require_role("student"))):
    row, msg = moderation.submit_appeal(
        student_id=session["student_data"]["student_id"],
        reason=body.reason,
        explanation=body.explanation,
        complaint_id=body.complaint_id,
        session_state=session,
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/moderation/appeals/review")
def review_appeal(body: AppealReviewIn, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    ok, msg = moderation.review_appeal(
        appeal_id=body.appeal_id,
        admin_staff_id=session["staff_data"].get("staff_id"),
        admin_role="administrator",
        decision=body.decision,
        admin_note=body.notes,
        duration_hours=body.duration_hours,
        session_state=session,
    )
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg}


@router.post("/api/moderation/complaints/{complaint_id}/open")
def open_complaint(complaint_id: str, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    return clean(moderation.admin_open(complaint_id, session["staff_data"].get("staff_id"), "administrator"))


@router.post("/api/moderation/complaints/{complaint_id}/decide")
def decide_complaint(complaint_id: str, body: DecideIn, session: dict = Depends(require_session)):
    if session.get("user_role") != "administrator":
        raise HTTPException(status_code=403, detail="Administrators only.")
    row, msg = moderation.admin_decide(
        complaint_id=complaint_id,
        admin_staff_id=session["staff_data"].get("staff_id"),
        admin_role="administrator",
        action=body.action,
        reason=body.notes,
        session_state=session,
    )
    if row is None and msg:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "detail": msg, "complaint": clean(row)}
