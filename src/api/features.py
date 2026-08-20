from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
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
from src.success import store
from src.success.intelligence import library, load_bundle, logs_by_student, profile_map, student_360
from src.success.notify import for_recipient
from src.success.risk_service import get_current_risk
from src.success.staff_auth import invite_staff
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
        if key in seen:
            continue
        seen.add(key)
        uniq.append(a)
    return uniq


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


class AppointmentIn(BaseModel):
    kind: str = "counsellor"
    starts_at: str | None = None


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


class DecideIn(BaseModel):
    action: str
    notes: str = ""


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
    return clean({
        "role": role,
        "actor": _actor(session),
        "demo": bool(bundle.get("demo") or session.get("demo_mode")),
        "modules": _modules(role),
        "profiles": profiles,
        "twins": twins,
        "mine": mine,
        "risk": risk,
        "cases": bundle.get("cases") or [],
        "recommendations": bundle.get("recommendations") or [],
        "academic": bundle.get("academic") or [],
        "lms": bundle.get("lms") or [],
        "alerts": _alerts(profiles),
        "library": library(),
        "notifications": notes[:30],
        "appointments": store.select("appointments", **({"student_id": student_id} if student_id is not None else {})),
        "tasks": store.select("recovery_tasks", **({"student_id": student_id} if student_id is not None else {})),
        "messages": store.select("messages") if role != "student" else [],
        "institution": inst,
        "mentorship": m_rows,
        "mentorship_admin": admin_m,
        "complaints": complaints,
        "appeals": appeals,
        "account": snap,
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
    store.insert("messages", {"sender": student.get("name"), "recipient": "counsellor", "channel": "in_app", "body": body.message, "status": "queued"})
    return {"ok": True, "detail": "Request queued for support staff."}


@router.post("/api/success/appointment")
def success_appointment(body: AppointmentIn, session: dict = Depends(require_role("student"))):
    store.insert("appointments", {
        "student_id": session["student_data"]["student_id"],
        "staff_name": body.kind,
        "kind": body.kind,
        "starts_at": body.starts_at or datetime.now().isoformat(timespec="minutes"),
        "status": "requested",
    })
    return {"ok": True, "detail": "Appointment requested."}


@router.post("/api/success/recommend")
def success_recommend(body: RecommendIn, session: dict = Depends(require_session)):
    bundle = load_bundle(session, teacher_id=(session.get("teacher_data") or {}).get("teacher_id"))
    profile = student_360(bundle, body.student_id)
    recs = (profile or {}).get("recommendations") or []
    if not recs:
        raise HTTPException(status_code=400, detail="No recommendation to submit.")
    rec = recs[0]
    store.insert("intervention_recommendations", {
        "student_id": body.student_id,
        "recommendation": rec.get("name"),
        "reason": rec.get("reason"),
        "confidence": rec.get("confidence"),
        "status": "pending",
    })
    return {"ok": True, "detail": "Queued for counsellor review."}


@router.post("/api/success/case")
def success_case(body: CaseIn, session: dict = Depends(require_session)):
    store.insert("intervention_cases", {
        "student_id": body.student_id,
        "owner": _actor(session),
        "priority": body.priority,
        "status": "open",
        "intervention_name": body.intervention_name,
        "notes": body.notes,
        "deadline": datetime.now().isoformat(),
    })
    return {"ok": True}


@router.post("/api/success/outcome")
def success_outcome(body: OutcomeIn, session: dict = Depends(require_session)):
    store.insert("intervention_outcomes", {
        "student_id": body.student_id,
        "result": body.result,
        "notes": body.notes,
        "actor": _actor(session),
    })
    return {"ok": True}


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
        answer = "Use Ask for support. A counsellor will see in-app requests."
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
    ref = (session.get("staff_data") or {}).get("staff_id") or (session.get("student_data") or {}).get("student_id")
    row, msg = mentorship.assign_mentorship(body.student_id, actor, ref, goal=body.goal, session_state=session)
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
    return clean(mentorship.messages(mentorship_id, **kwargs))


@router.post("/api/mentorship/{mentorship_id}/messages")
def mentorship_post(mentorship_id: str, body: MessageIn, session: dict = Depends(require_session)):
    kwargs = {"body": body.body}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    return clean(mentorship.post_message(mentorship_id, **kwargs))


@router.post("/api/mentorship/{mentorship_id}/sessions")
def mentorship_session(mentorship_id: str, body: SessionIn, session: dict = Depends(require_session)):
    kwargs = {"title": body.title, "notes": body.notes}
    if session.get("user_role") == "student":
        kwargs["student_id"] = session["student_data"]["student_id"]
    else:
        kwargs["staff_id"] = (session.get("staff_data") or {}).get("staff_id")
    return clean(mentorship.add_session(mentorship_id, **kwargs))


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
