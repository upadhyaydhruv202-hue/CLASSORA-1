from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
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
from src.academic import service as academic
from src.cohort import service as cohort
from src.dropout import service as dropout
from src.rewards import service as rewards
from src.attendance import service as attendance
from src.predictions import service as predictions
from src.communities import service as communities
from src.auth.session import session_payload
from src.auth.tokens import encode_token

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
    if role in ("teacher", "administrator"):
        options += [
            "Institution success", "Counsellor", "Student 360", "Early warning", "Recommender",
            "Human review", "Cases", "Outcomes", "Recovery", "What-if", "Digital Twin",
            "Explainable AI", "Predictive Twin", "Reports", "Search", "Import", "Monitoring",
            "Health", "Settings", "Assistant", "Notifications", "Communication", "Appointments",
            "Academic", "Attendance intel", "LMS", "Institutional Anomalies", "Dropout Root Causes",
            "CLASSORA Rewards", "Secure Attendance", "Predictive Intelligence",
        ]
    if role == "counsellor":
        options += [
            "Counsellor", "Student 360", "Early warning", "Recommender",
            "Cases", "Outcomes", "Recovery", "Digital Twin",
            "Explainable AI", "Predictive Twin", "Reports", "Search", "Import", "Monitoring",
            "Health", "Settings", "Assistant", "Notifications", "Communication", "Appointments",
            "Academic", "Attendance intel", "LMS", "Institutional Anomalies",
            "CLASSORA Rewards", "Predictive Intelligence",
        ]
    if role in ("faculty", "mentor"):
        options += ["Digital Twin", "Explainable AI", "Predictive Twin", "What-if", "Notifications", "CLASSORA Rewards", "Predictive Intelligence"]
    if role == "merchant":
        options = ["Merchant Rewards"]
    if role == "administrator":
        options += ["Ecosystem analytics", "Mentorship admin", "Complaint Management", "Academic Resources", "Communities"]
    if role in ("faculty", "mentor", "teacher"):
        options += ["Faculty portal"]
    if role in ("faculty", "mentor", "counsellor"):
        options += ["Anonymous Mentorship"]
    if role in ("faculty", "mentor", "counsellor", "teacher"):
        options += ["Report Student"]
    if role == "student":
        options = ["Student snapshot", "My Digital Twin", "My Risk", "AI Explanation", "Recovery AI",
                   "Future trajectory", "Interventions", "Notifications", "Ask for support",
                   "Anonymous Mentorship", "Academic Resources", "My Rewards", "Verify Attendance",
                   "Predictive Intelligence", "Communities", "Account"]
    return list(dict.fromkeys(options))


def _appointment_kind(value) -> str:
    raw = value.get("kind") if isinstance(value, dict) else value
    text = str(raw or "").strip().lower()
    if text in ("mentor", "mentoring", "mentorship"):
        return "mentor"
    if text in ("counsellor", "counselor", "counselling", "counseling", ""):
        return "counsellor"
    return ""


def _can_connect_appointment(role: str, kind: str) -> bool:
    if role == "administrator":
        return True
    if kind == "counsellor":
        return role == "counsellor"
    if kind == "mentor":
        return role in ("mentor", "faculty")
    return False


def _visible_appointments(role: str, appointments):
    rows = list(appointments or [])
    if role == "counsellor":
        return [row for row in rows if _appointment_kind(row) == "counsellor"]
    if role in ("mentor", "faculty"):
        return [row for row in rows if _appointment_kind(row) == "mentor"]
    return rows


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


class AcademicResourceIn(BaseModel):
    title: str = ""
    description: str = ""
    year_id: str = ""
    yearId: str = ""
    semester_id: str = ""
    semesterId: str = ""
    subject_id: int | str | None = None
    subjectId: int | str | None = None
    resource_type_id: int | str | None = None
    resourceTypeId: int | str | None = None
    source_id: int | str | None = None
    sourceId: int | str | None = None
    original_url: str = ""
    originalUrl: str = ""
    resource_format: str = ""
    resourceFormat: str = ""
    tags: str = ""
    display_order: int | None = None
    displayOrder: int | None = None
    is_active: bool | None = None
    isActive: bool | None = None


class AcademicSubjectIn(BaseModel):
    name: str = ""
    code: str = ""
    description: str = ""
    year_id: str = ""
    yearId: str = ""
    semester_id: str = ""
    semesterId: str = ""
    status: str = ""


class AcademicSourceIn(BaseModel):
    name: str = ""
    code: str = ""
    website_url: str = ""
    websiteUrl: str = ""
    description: str = ""
    is_active: bool | None = None
    isActive: bool | None = None


class AcademicTypeIn(BaseModel):
    name: str = ""
    code: str = ""
    display_order: int | None = None
    displayOrder: int | None = None


class AcademicReportIn(BaseModel):
    reason: str = "Resource link is not working"


class AcademicReportReviewIn(BaseModel):
    status: str = ""
    decision: str = ""


class AcademicSyncIn(BaseModel):
    source_id: str | int | None = None
    sourceId: str | int | None = None


class AnomalyNoteIn(BaseModel):
    note: str = ""


class AnomalySettingsIn(BaseModel):
    min_cohort_size: int | None = None
    min_baseline_periods: int | None = None
    current_window_days: int | None = None
    baseline_weeks: int | None = None
    min_affected_percent: float | None = None
    min_anomaly_score: float | None = None
    watch_score: float | None = None
    moderate_score: float | None = None
    high_score: float | None = None
    critical_score: float | None = None
    recovery_periods: int | None = None
    affected_gap_pp: float | None = None
    volume_collapse_ratio: float | None = None
    notify_severities: list[str] | None = None


class DropoutSettingsIn(BaseModel):
    min_factor_sample_size: int | None = None
    min_dropout_observations: int | None = None
    min_periods: int | None = None
    suppress_group_size: int | None = None
    low_attendance_threshold: float | None = None
    low_completion_threshold: float | None = None
    fail_mark: float | None = None
    high_rate_threshold: float | None = None
    high_volume_threshold: int | None = None


class DropoutOutcomeIn(BaseModel):
    student_id: int | None = None
    studentId: int | None = None
    status: str = ""
    period: str = ""
    notes: str = ""


class DropoutImportIn(BaseModel):
    csv: str = ""
    text: str = ""


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
    if role == "merchant":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
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
            try:
                rewards.tick_jobs(session)
            except Exception:
                pass
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
        appointments = _visible_appointments(role, store.select("appointments", student_id=sid) or [])
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
            "anomalySummary": None,
            "rewardSummary": rewards.student_summary(session),
            "predictionSummary": _prediction_summary(session),
            "communitySummary": _community_summary(session),
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
        elif role == "teacher" and teacher_id is not None:
            notes = list(for_recipient(role="teacher", recipient_id=teacher_id) or [])
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
    appointments = _visible_appointments(role, appointments)
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
    anomaly_summary = None
    if role in ("administrator", "teacher", "counsellor"):
        try:
            anomaly_summary = cohort.summary(session)
        except Exception:
            anomaly_summary = {"available": False}
    dropout_summary = None
    if role in dropout.VIEW_ROLES:
        try:
            dropout_summary = dropout.summary(session)
        except Exception:
            dropout_summary = {"available": False}
    try:
        rewards.tick_jobs(session)
    except Exception:
        pass
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
        "anomalySummary": anomaly_summary,
        "dropoutSummary": dropout_summary,
        "rewardSummary": None,
        "predictionSummary": None,
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
    kind = _appointment_kind(body.kind)
    if kind not in ("counsellor", "mentor"):
        raise HTTPException(status_code=400, detail="Choose counselling or mentoring.")
    saved = store.insert("appointments", {
        "student_id": student["student_id"],
        "staff_name": kind,
        "kind": kind,
        "starts_at": body.starts_at or datetime.now().isoformat(timespec="minutes"),
        "status": "requested",
    })
    _must_save(saved, "Could not save the appointment request.")
    if kind == "mentor":
        notify(
            role="mentor",
            recipient_id="caseload",
            title="Mentoring session requested",
            body=f"Student ID {student.get('student_id')} asked for a mentor. Open Appointments to connect privately.",
        )
        notify(
            role="student",
            recipient_id=student.get("student_id"),
            title="Mentoring request sent",
            body="A mentor will review your request. Watch Notifications, then open Anonymous Mentorship when it is accepted.",
        )
        return {
            "ok": True,
            "kind": kind,
            "status": "requested",
            "appointment": saved[0],
            "detail": "Mentoring requested. Wait for a mentor to open a private chat.",
        }
    notify(
        role="counsellor",
        recipient_id="caseload",
        title="Counselling session requested",
        body=f"Student ID {student.get('student_id')} asked for counselling. Open Appointments to connect privately.",
    )
    notify(
        role="student",
        recipient_id=student.get("student_id"),
        title="Counselling request sent",
        body="A counsellor will review your request. Watch Notifications, then open Anonymous Mentorship when it is accepted.",
    )
    return {
        "ok": True,
        "kind": kind,
        "status": "requested",
        "appointment": saved[0],
        "detail": "Counselling requested. Wait for a counsellor to open a private chat.",
    }


@router.post("/api/success/appointment/connect")
def success_appointment_connect(body: AppointmentConnectIn, session: dict = Depends(require_session)):
    """Accept a counselling or mentoring request by opening alias-only chat."""
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
    kind = _appointment_kind(appt)
    if not _can_connect_appointment(role, kind):
        if kind == "counsellor":
            raise HTTPException(status_code=403, detail="Only a counsellor can accept a counselling request.")
        if kind == "mentor":
            raise HTTPException(status_code=403, detail="Only a mentor can accept a mentoring request.")
        raise HTTPException(status_code=403, detail="You cannot accept this request.")
    try:
        student_id = int(appt.get("student_id"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Appointment is missing a student.")
    prefer = staff_id if role != "administrator" else None
    if kind == "mentor":
        goal = "Private mentoring chat after student request."
        notes = "Private mentoring chat opened in Anonymous Mentorship."
        detail_fallback = "Mentoring chat opened. Continue in Anonymous Mentorship. Messages use aliases only."
    else:
        goal = "Private counselling chat after student request."
        notes = "Private counselling chat opened in Anonymous Mentorship."
        detail_fallback = "Counselling chat opened. Continue in Anonymous Mentorship. Messages use aliases only."
    row, msg = mentorship.assign_mentorship(
        student_id,
        role,
        staff_id,
        goal=goal,
        session_state=session,
        prefer_staff_id=prefer,
        kind=kind,
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    view = row
    if role != "student":
        view = mentorship.faculty_view(row.get("mentorshipId"), staff_id) or row
    store.update("appointments", {"id": body.appointment_id}, {
        "status": "connected",
        "notes": notes,
    })
    return {
        "ok": True,
        "kind": kind,
        "status": "connected",
        "detail": msg or detail_fallback,
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
    if session.get("user_role") == "merchant":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    if session.get("user_role") == "student":
        raise HTTPException(status_code=403, detail="Staff search the student directory.")
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    bundle = load_bundle(session, teacher_id=teacher_id)
    profiles = search_profiles(profile_map(bundle), q)
    return {"ok": True, "query": q, "count": len(profiles), "results": clean(report_rows(profiles))}


@router.get("/api/success/report")
def success_report(session: dict = Depends(require_session)):
    if session.get("user_role") == "merchant":
        raise HTTPException(status_code=403, detail="FORBIDDEN")
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


def _academic_admin(session: dict) -> bool:
    return session.get("user_role") == "administrator"


def _academic_viewer(session: dict) -> bool:
    return session.get("user_role") in (
        "student", "teacher", "administrator", "counsellor", "faculty", "mentor",
    )


def _require_academic_viewer(session: dict):
    if not _academic_viewer(session):
        raise HTTPException(status_code=403, detail="Not allowed for this portal.")


def _require_academic_admin(session: dict):
    if not _academic_admin(session):
        raise HTTPException(status_code=403, detail="Administrators only.")


@router.get("/api/academic-years")
def academic_years(session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    return {"years": academic.years()}


@router.get("/api/academic-semesters")
def academic_semesters(year: str = "", session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    return {"semesters": academic.semesters(academic.resolve_year_id(year) or year or None)}


@router.get("/api/academic-subjects")
def academic_subjects(year: str = "", semester: str = "", session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    err = academic.ensure_catalog()
    if err:
        return {"subjects": [], "detail": err, "installed": False}
    return {
        "subjects": academic.subjects(
            year_id=academic.resolve_year_id(year) or year or None,
            semester_id=academic.resolve_semester_id(semester) or semester or None,
            include_inactive=_academic_admin(session),
        ),
        "installed": True,
    }


@router.get("/api/academic-resource-types")
def academic_resource_types(session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    err = academic.ensure_catalog()
    if err:
        return {"types": [], "detail": err, "installed": False}
    return {"types": academic.types(include_inactive=_academic_admin(session)), "installed": True}


@router.get("/api/academic-sources")
def academic_sources(session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    err = academic.ensure_catalog()
    if err:
        return {"sources": [], "detail": err, "installed": False}
    return {"sources": academic.sources(include_inactive=_academic_admin(session)), "installed": True}


@router.get("/api/academic-resources/catalog")
def academic_catalog(year: str = "", semester: str = "", session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    return clean(academic.catalog(
        year_id=academic.resolve_year_id(year) or year or None,
        semester_id=academic.resolve_semester_id(semester) or semester or None,
        include_inactive=_academic_admin(session),
    ))


@router.post("/api/academic-resources/sync")
def academic_resource_sync(body: AcademicSyncIn | None = None, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    payload = body.model_dump() if body else {}
    report, msg = academic.sync_registered_sources(
        source_id=payload.get("source_id") or payload.get("sourceId"),
        actor=_actor(session),
    )
    if report is None:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "report": clean(report)}


@router.get("/api/academic-resources")
def academic_resource_list(
    year: str = "",
    semester: str = "",
    subject: str = "",
    type: str = "",
    source: str = "",
    search: str = "",
    sort: str = "recent",
    page: int = 1,
    limit: int = 20,
    session: dict = Depends(require_session),
):
    _require_academic_viewer(session)
    return clean(academic.list_resources(
        year_id=year or None,
        semester_id=semester or None,
        subject_id=subject or None,
        type_code=type or None,
        source_code=source or None,
        search=search,
        sort=sort,
        page=page,
        limit=limit,
        include_inactive=_academic_admin(session),
    ))


@router.get("/api/academic-resources/{resource_id}")
def academic_resource_one(resource_id: str, session: dict = Depends(require_session)):
    _require_academic_viewer(session)
    row, msg = academic.get_resource(resource_id, include_inactive=_academic_admin(session))
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return clean(row)


@router.post("/api/academic-resources")
def academic_resource_create(body: AcademicResourceIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.create_resource(body.model_dump(), actor=_actor(session))
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "resource": clean(row)}


@router.put("/api/academic-resources/{resource_id}")
def academic_resource_update(resource_id: str, body: AcademicResourceIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.update_resource(resource_id, body.model_dump(exclude_unset=True))
    if not row:
        code = 404 if msg == "Resource not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "resource": clean(row)}


@router.delete("/api/academic-resources/{resource_id}")
def academic_resource_delete(resource_id: str, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.set_resource_active(resource_id, False)
    if not row:
        code = 404 if msg == "Resource not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "resource": clean(row), "detail": "Resource deactivated."}


@router.post("/api/academic-resources/{resource_id}/verify")
def academic_resource_verify(resource_id: str, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.verify_resource(resource_id)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "resource": clean(row)}


@router.post("/api/academic-resources/{resource_id}/report")
def academic_resource_report(resource_id: str, body: AcademicReportIn, session: dict = Depends(require_role("student"))):
    student_id = (session.get("student_data") or {}).get("student_id")
    if student_id is None:
        raise HTTPException(status_code=403, detail="Not allowed for this portal.")
    row, msg = academic.report_broken(resource_id, student_id=student_id, reason=body.reason)
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "report": clean(row), "detail": "Thanks. We recorded that this link may be unavailable."}


@router.post("/api/academic-subjects")
def academic_subject_create(body: AcademicSubjectIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.create_subject(body.model_dump())
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "subject": clean(row)}


@router.put("/api/academic-subjects/{subject_id}")
def academic_subject_update(subject_id: str, body: AcademicSubjectIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.update_subject(subject_id, body.model_dump(exclude_unset=True))
    if not row:
        code = 404 if msg == "Subject not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "subject": clean(row)}


@router.post("/api/academic-sources")
def academic_source_create(body: AcademicSourceIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.create_source(body.model_dump())
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "source": clean(row)}


@router.put("/api/academic-sources/{source_id}")
def academic_source_update(source_id: str, body: AcademicSourceIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.update_source(source_id, body.model_dump(exclude_unset=True))
    if not row:
        code = 404 if msg == "Source not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "source": clean(row)}


@router.post("/api/academic-resource-types")
def academic_type_create(body: AcademicTypeIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.create_type(body.model_dump())
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "type": clean(row)}


@router.get("/api/academic-resource-reports")
def academic_report_list(status: str = "", session: dict = Depends(require_session)):
    _require_academic_admin(session)
    return {"reports": clean(academic.list_reports(status=status or None))}


@router.post("/api/academic-resource-reports/{report_id}/review")
def academic_report_review(report_id: str, body: AcademicReportReviewIn, session: dict = Depends(require_session)):
    _require_academic_admin(session)
    row, msg = academic.review_report(report_id, body.decision or body.status)
    if not row:
        code = 404 if msg == "Report not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "report": clean(row)}


def _cohort_viewer(session: dict) -> bool:
    return session.get("user_role") in cohort.VIEW_ROLES


def _require_cohort_viewer(session: dict):
    if not _cohort_viewer(session):
        raise HTTPException(status_code=403, detail="Institutional anomaly analytics are limited to authorized staff.")


def _require_cohort_analyzer(session: dict):
    if session.get("user_role") not in cohort.ANALYZE_ROLES:
        raise HTTPException(status_code=403, detail="Only authorized administrators or faculty can run analysis.")


def _require_cohort_manager(session: dict):
    if session.get("user_role") not in cohort.MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="Only authorized staff can update institutional anomalies.")


def _cohort_actor(session: dict) -> str:
    return _actor(session) or session.get("user_role") or ""


@router.get("/api/institutional-anomalies")
def institutional_anomaly_list(
    severity: str = "",
    status: str = "",
    section: str = "",
    semester: str = "",
    course: str = "",
    metric: str = "",
    cohort_type: str = "",
    search: str = "",
    sort: str = "newest",
    start: str = "",
    end: str = "",
    session: dict = Depends(require_session),
):
    _require_cohort_viewer(session)
    rows = cohort.list_events(session, {
        "severity": severity,
        "status": status,
        "section": section,
        "semester": semester,
        "course": course,
        "metric": metric,
        "cohort_type": cohort_type,
        "search": search,
        "sort": sort,
        "start": start,
        "end": end,
    })
    return {"anomalies": clean(rows), "count": len(rows)}


@router.get("/api/institutional-anomalies/summary")
def institutional_anomaly_summary(session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    return clean(cohort.summary(session))


@router.get("/api/institutional-anomalies/settings")
def institutional_anomaly_settings_get(session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    return clean(cohort.settings_record())


@router.put("/api/institutional-anomalies/settings")
def institutional_anomaly_settings_put(body: AnomalySettingsIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in cohort.SETTINGS_ROLES:
        raise HTTPException(status_code=403, detail="Administrators only.")
    cfg = cohort.save_config(body.model_dump(exclude_none=True), actor=_cohort_actor(session))
    return {"ok": True, "settings": clean(cfg)}


@router.post("/api/institutional-anomalies/analyze")
def institutional_anomaly_analyze(session: dict = Depends(require_session)):
    _require_cohort_analyzer(session)
    try:
        result = cohort.run_analysis(session, actor=_cohort_actor(session))
    except Exception:
        raise HTTPException(status_code=500, detail="Anomaly analysis is currently unavailable.")
    return {
        "ok": True,
        "coldStart": bool(result.get("cold_start")),
        "insufficientHistory": bool(result.get("insufficient_history")),
        "cohortsAnalyzed": result.get("cohorts_analyzed") or 0,
        "anomalies": len(result.get("events") or []),
        "persist": clean(result.get("persist") or {}),
        "dimensions": result.get("dimensions"),
        "disclaimer": result.get("disclaimer"),
        "durationMs": result.get("durationMs"),
    }


@router.get("/api/institutional-anomalies/{anomaly_id}")
def institutional_anomaly_one(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    row, msg = cohort.get_event(anomaly_id, session, include_students=session.get("user_role") == "administrator")
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"anomaly": clean(row)}


@router.get("/api/institutional-anomalies/{anomaly_id}/timeline")
def institutional_anomaly_timeline(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    row, msg = cohort.timeline(anomaly_id, session)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return clean(row)


@router.get("/api/institutional-anomalies/{anomaly_id}/evidence")
def institutional_anomaly_evidence(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    row, msg = cohort.evidence(anomaly_id, session)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return clean(row)


@router.get("/api/institutional-anomalies/{anomaly_id}/cohort")
def institutional_anomaly_cohort(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    row, msg = cohort.cohort_view(anomaly_id, session)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return clean(row)


@router.get("/api/institutional-anomalies/{anomaly_id}/notes")
def institutional_anomaly_notes(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_viewer(session)
    rows, msg = cohort.list_notes(anomaly_id, session)
    if msg:
        raise HTTPException(status_code=404, detail=msg)
    return {"notes": clean(rows)}


@router.post("/api/institutional-anomalies/{anomaly_id}/notes")
def institutional_anomaly_note_add(anomaly_id: str, body: AnomalyNoteIn, session: dict = Depends(require_session)):
    _require_cohort_manager(session)
    row, msg = cohort.add_note(anomaly_id, session, body.note, actor=_cohort_actor(session))
    if not row:
        code = 404 if msg == "Anomaly not found." else 400
        raise HTTPException(status_code=code, detail=msg)
    return {"ok": True, "note": clean(row)}


@router.post("/api/institutional-anomalies/{anomaly_id}/acknowledge")
def institutional_anomaly_ack(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_manager(session)
    row, msg = cohort.set_status(anomaly_id, session, "ACKNOWLEDGED", actor=_cohort_actor(session))
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "anomaly": clean(row)}


@router.post("/api/institutional-anomalies/{anomaly_id}/investigate")
def institutional_anomaly_investigate(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_manager(session)
    row, msg = cohort.set_status(anomaly_id, session, "INVESTIGATING", actor=_cohort_actor(session))
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "anomaly": clean(row)}


@router.post("/api/institutional-anomalies/{anomaly_id}/resolve")
def institutional_anomaly_resolve(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_manager(session)
    row, msg = cohort.set_status(anomaly_id, session, "RESOLVED", actor=_cohort_actor(session))
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "anomaly": clean(row)}


@router.post("/api/institutional-anomalies/{anomaly_id}/dismiss")
def institutional_anomaly_dismiss(anomaly_id: str, session: dict = Depends(require_session)):
    _require_cohort_manager(session)
    row, msg = cohort.set_status(anomaly_id, session, "DISMISSED", actor=_cohort_actor(session))
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    return {"ok": True, "anomaly": clean(row)}


def _dropout_viewer(session: dict) -> bool:
    return session.get("user_role") in dropout.VIEW_ROLES


def _require_dropout_viewer(session: dict):
    if not _dropout_viewer(session):
        raise HTTPException(status_code=403, detail="Institutional dropout analytics are limited to authorized leadership.")


def _require_dropout_analyzer(session: dict):
    if session.get("user_role") not in dropout.ANALYZE_ROLES:
        raise HTTPException(status_code=403, detail="Only authorized administrators or faculty can run dropout analysis.")


def _require_dropout_admin(session: dict):
    if session.get("user_role") not in dropout.SETTINGS_ROLES:
        raise HTTPException(status_code=403, detail="Administrators only.")


def _dropout_actor(session: dict) -> str:
    return _actor(session) or session.get("user_role") or ""


@router.get("/api/institutional-dropout/overview")
def institutional_dropout_overview(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_analysis_viewed", "institutional-dropout/overview", session.get("user_role") or "")
    return clean(dropout.overview(session))


@router.get("/api/institutional-dropout/summary")
def institutional_dropout_summary(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    return clean(dropout.summary(session))


@router.get("/api/institutional-dropout/settings")
def institutional_dropout_settings_get(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    return clean(dropout.settings_record())


@router.put("/api/institutional-dropout/settings")
def institutional_dropout_settings_put(body: DropoutSettingsIn, session: dict = Depends(require_session)):
    _require_dropout_admin(session)
    cfg = dropout.save_config(body.model_dump(exclude_none=True), actor=_dropout_actor(session))
    dropout.audit(_dropout_actor(session), "dropout_settings_updated", "institutional-dropout/settings")
    return {"ok": True, "settings": clean(cfg)}


@router.post("/api/institutional-dropout/analyze")
def institutional_dropout_analyze(session: dict = Depends(require_session)):
    _require_dropout_analyzer(session)
    try:
        result = dropout.run_analysis(session, actor=_dropout_actor(session))
    except Exception:
        raise HTTPException(status_code=500, detail="Dropout analysis is currently unavailable.")
    dropout.audit(_dropout_actor(session), "dropout_analysis_run", "institutional-dropout/analyze", session.get("user_role") or "")
    return {
        "ok": True,
        "insufficient": bool(result.get("insufficient")),
        "reason": result.get("reason"),
        "overview": clean(result.get("overview") or {}),
        "factors": len(result.get("factors") or []),
        "persist": clean(result.get("persist") or {}),
        "disclaimer": result.get("disclaimer"),
        "durationMs": result.get("durationMs"),
        "version": result.get("version"),
    }


@router.get("/api/institutional-dropout/trends")
def institutional_dropout_trends(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_trends_viewed", "institutional-dropout/trends")
    return {"trends": clean(dropout.get_section(session, "trends", []) or [])}


@router.get("/api/institutional-dropout/factors")
def institutional_dropout_factors(
    factor: str = "",
    classification: str = "",
    confidence: str = "",
    session: dict = Depends(require_session),
):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_factors_viewed", "institutional-dropout/factors")
    rows = dropout.filtered_factors(session, factor=factor, classification=classification, confidence=confidence)
    return {"factors": clean(rows), "count": len(rows)}


@router.get("/api/institutional-dropout/factors/{factor_id}")
def institutional_dropout_factor_one(factor_id: str, session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    row, msg = dropout.factor_detail(session, factor_id)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    dropout.audit(_dropout_actor(session), "dropout_factor_viewed", f"institutional-dropout/factors/{factor_id}")
    return {"factor": clean(row)}


@router.get("/api/institutional-dropout/departments")
def institutional_dropout_departments(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_sections_viewed", "institutional-dropout/departments")
    return {
        "unavailable": True,
        "reason": dropout.engine.DEPARTMENT_UNAVAILABLE,
        "dimension": "section",
        "sections": clean((dropout.get_section(session, "slices", {}) or {}).get("sections") or []),
    }


@router.get("/api/institutional-dropout/departments/{department_id}")
def institutional_dropout_department_one(department_id: str, session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    row, msg = dropout.slice_detail(session, "section", department_id)
    if not row:
        raise HTTPException(status_code=404, detail=msg)
    dropout.audit(_dropout_actor(session), "dropout_section_viewed", f"institutional-dropout/departments/{department_id}")
    return {"section": clean(row), "dimension": "section"}


@router.get("/api/institutional-dropout/semesters")
def institutional_dropout_semesters(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_semesters_viewed", "institutional-dropout/semesters")
    return {"semesters": clean((dropout.get_section(session, "slices", {}) or {}).get("semesters") or [])}


@router.get("/api/institutional-dropout/courses")
def institutional_dropout_courses(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_courses_viewed", "institutional-dropout/courses")
    return {"courses": clean((dropout.get_section(session, "slices", {}) or {}).get("courses") or [])}


@router.get("/api/institutional-dropout/heatmap")
def institutional_dropout_heatmap(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_heatmap_viewed", "institutional-dropout/heatmap")
    return {"heatmap": clean(dropout.get_section(session, "heatmap", []) or [])}


@router.get("/api/institutional-dropout/intersections")
def institutional_dropout_intersections(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_intersections_viewed", "institutional-dropout/intersections")
    return {"intersections": clean(dropout.get_section(session, "intersections", []) or [])}


@router.get("/api/institutional-dropout/recommendations")
def institutional_dropout_recommendations(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    dropout.audit(_dropout_actor(session), "dropout_recommendations_viewed", "institutional-dropout/recommendations")
    return {"recommendations": clean(dropout.get_section(session, "recommendations", []) or [])}


@router.get("/api/institutional-dropout/compare")
def institutional_dropout_compare(
    kind: str = "section",
    left: str = "",
    right: str = "",
    session: dict = Depends(require_session),
):
    _require_dropout_viewer(session)
    row, msg = dropout.compare(session, kind, left, right)
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    dropout.audit(_dropout_actor(session), "dropout_compare_viewed", "institutional-dropout/compare", kind)
    return clean(row)


@router.get("/api/institutional-dropout/report")
def institutional_dropout_report(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    payload = dropout.report_payload(session)
    if not payload:
        raise HTTPException(status_code=404, detail="No analysis has been run yet.")
    dropout.audit(_dropout_actor(session), "dropout_report_generated", "institutional-dropout/report")
    return clean(payload)


@router.get("/api/institutional-dropout/export")
def institutional_dropout_export(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    text = dropout.csv_text(session)
    if not text:
        raise HTTPException(status_code=404, detail="No analysis has been run yet.")
    dropout.audit(_dropout_actor(session), "dropout_export_generated", "institutional-dropout/export")
    return Response(content=text, media_type="text/csv", headers={"Content-Disposition": "attachment; filename=institutional-dropout.csv"})


@router.get("/api/institutional-dropout/first-year")
def institutional_dropout_first_year(session: dict = Depends(require_session)):
    _require_dropout_viewer(session)
    data = dropout.latest_analysis(session)
    if not data:
        raise HTTPException(status_code=404, detail="No analysis has been run yet.")
    factor, _msg = dropout.factor_detail(session, "FIRST_YEAR")
    dropout.audit(_dropout_actor(session), "dropout_first_year_viewed", "institutional-dropout/first-year")
    return clean({
        "available": bool(factor and factor.get("available") and factor.get("classification") != "INSUFFICIENT_DATA"),
        "shareOfDropouts": data.get("firstYearShare"),
        "factor": factor,
        "unavailable": (data.get("unavailable") or {}).get("FIRST_YEAR"),
    })


@router.get("/api/institutional-dropout/outcomes")
def institutional_dropout_outcomes(session: dict = Depends(require_session)):
    _require_dropout_admin(session)
    return {"outcomes": clean(dropout.list_outcomes()), "statuses": list(dropout.engine.ALL_OUTCOME_STATUSES)}


@router.post("/api/institutional-dropout/outcomes")
def institutional_dropout_outcome_create(body: DropoutOutcomeIn, session: dict = Depends(require_session)):
    _require_dropout_admin(session)
    row, msg = dropout.record_outcome(
        body.student_id if body.student_id is not None else body.studentId,
        body.status,
        period=body.period,
        notes=body.notes,
        actor=_dropout_actor(session),
    )
    if not row:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "outcome": clean(row)}


@router.post("/api/institutional-dropout/outcomes/import")
def institutional_dropout_outcome_import(body: DropoutImportIn, session: dict = Depends(require_session)):
    _require_dropout_admin(session)
    rows, msg = dropout.import_outcomes(body.csv or body.text, actor=_dropout_actor(session))
    if msg:
        raise HTTPException(status_code=400, detail=msg)
    return {"ok": True, "imported": len(rows)}


class RewardAchievementIn(BaseModel):
    student_id: int | None = None
    studentId: int | None = None
    category: str = ""
    achievement_type: str = ""
    achievementType: str = ""
    achievement_level: str = ""
    achievementLevel: str = ""
    title: str = ""
    description: str = ""
    organization: str = ""
    occurred_at: str = ""
    occurredAt: str = ""
    certificate_id: str = ""
    certificateId: str = ""
    event_key: str = ""
    eventKey: str = ""
    evidence: dict | None = None
    points: int | None = None
    overrideReason: str = ""
    reason: str = ""
    idempotency_key: str = ""
    idempotencyKey: str = ""


class RewardReviewIn(BaseModel):
    decision: str = ""
    reason: str = ""


class RewardAdjustIn(BaseModel):
    student_id: int | None = None
    studentId: int | None = None
    points: int | None = None
    reason: str = ""


class RewardReverseIn(BaseModel):
    reason: str = ""


class RewardSettingsIn(BaseModel):
    rewards_enabled: bool | None = None
    merchant_redemption_enabled: bool | None = None
    achievement_submission_enabled: bool | None = None
    leaderboard_enabled: bool | None = None
    automatic_rewards_enabled: bool | None = None
    education_level: str | None = None
    point_expiry_days: int | None = None
    voucher_expiry_days: int | None = None
    direct_award_max: int | None = None
    daily_student_cap: int | None = None
    weekly_student_cap: int | None = None
    monthly_student_cap: int | None = None
    daily_issuer_cap: int | None = None
    self_approval: bool | None = None
    allow_manual_point_override: bool | None = None


class RewardPolicyIn(BaseModel):
    id: int | str | None = None
    category: str = ""
    achievement_type: str = ""
    achievementType: str = ""
    achievement_level: str = ""
    achievementLevel: str = ""
    points: int | None = None
    approvalRequired: bool | None = None
    approval_required: bool | None = None
    active: bool | None = None
    validFrom: str | None = None
    validUntil: str | None = None


class RewardMerchantIn(BaseModel):
    id: int | str | None = None
    name: str = ""
    category: str = "OTHER"
    location: str = ""
    contact: str = ""
    description: str = ""
    active: bool | None = None
    accessCode: str = ""
    access_code: str = ""


class RewardOfferIn(BaseModel):
    id: int | str | None = None
    merchantId: int | None = None
    merchant_id: int | None = None
    title: str = ""
    description: str = ""
    discountType: str = "PERCENTAGE"
    discount_type: str = ""
    discountValue: int | None = None
    discount_value: int | None = None
    pointsCost: int | None = None
    points_cost: int | None = None
    minimumPurchase: int | None = None
    maximumDiscount: int | None = None
    redemptionLimit: int | None = None
    perStudentLimit: int | None = None
    validFrom: str | None = None
    validUntil: str | None = None
    active: bool | None = None
    terms: str = ""


class RewardClaimIn(BaseModel):
    idempotencyKey: str = ""
    idempotency_key: str = ""


class RewardRedeemIn(BaseModel):
    token: str = ""


class RewardMerchantLoginIn(BaseModel):
    merchant_id: int | str | None = None
    merchantId: int | str | None = None
    access_code: str = ""
    accessCode: str = ""


class RewardCancelIn(BaseModel):
    reason: str = ""
    refund: bool = True


def _reward_error(msg: str):
    mapping = {
        "FEATURE_DISABLED": 403,
        "FORBIDDEN": 403,
        "UNAUTHORIZED": 401,
        "SELF_APPROVAL_FORBIDDEN": 403,
        "MERCHANT_NOT_AUTHORIZED": 403,
        "NOT_FOUND": 404,
        "RATE_LIMITED": 429,
    }
    raise HTTPException(status_code=mapping.get(msg, 400), detail=msg)


def _require_reward_viewer(session: dict):
    if session.get("user_role") not in rewards.VIEW_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")


@router.post("/api/rewards/merchant/login")
def rewards_merchant_login(body: RewardMerchantLoginIn):
    merchant, msg = rewards.merchant_login(body.merchant_id if body.merchant_id is not None else body.merchantId, body.access_code or body.accessCode)
    if not merchant:
        _reward_error(msg)
    session = session_payload(role="merchant", merchant=merchant)
    return {"ok": True, "token": encode_token(session), "session": clean(session)}


@router.get("/api/rewards/wallet")
def rewards_wallet(student_id: int | None = None, session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    if session.get("user_role") == "student":
        sid = (session.get("student_data") or {}).get("student_id")
    else:
        sid = student_id
        if sid is None:
            raise HTTPException(status_code=400, detail="student_id is required.")
    try:
        rewards.tick_jobs(session)
    except Exception:
        pass
    return clean({"wallet": rewards.wallet_for(sid)})


@router.get("/api/rewards/transactions")
def rewards_transactions(student_id: int | None = None, limit: int = 50, offset: int = 0, session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    rows, total = rewards.list_transactions(session, student_id=student_id, limit=limit, offset=offset)
    return {"transactions": clean(rows), "total": total}


@router.get("/api/rewards/achievements")
def rewards_achievements(student_id: int | None = None, status: str = "", limit: int = 50, offset: int = 0, session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    rows, total = rewards.list_achievements(session, student_id=student_id, status=status, limit=limit, offset=offset)
    return {"achievements": clean(rows), "total": total}


@router.post("/api/rewards/achievements")
def rewards_achievement_create(body: RewardAchievementIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in ("student",) + rewards.STAFF_AWARD_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.submit_achievement(session, body.model_dump())
    if not row:
        _reward_error(msg)
    return {"ok": True, "achievement": clean(row), "notice": msg or None}


@router.post("/api/rewards/achievements/{achievement_id}/verify")
def rewards_achievement_verify(achievement_id: str, body: RewardReviewIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.VERIFY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.review_achievement(session, achievement_id, body.decision or "APPROVE", body.reason)
    if not row:
        _reward_error(msg)
    return {"ok": True, "achievement": clean(row)}


@router.post("/api/rewards/requests/{achievement_id}/approve")
def rewards_request_approve(achievement_id: str, body: RewardReviewIn | None = None, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.APPROVE_ROLES + rewards.VERIFY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.review_achievement(session, achievement_id, "APPROVE", (body.reason if body else ""))
    if not row:
        _reward_error(msg)
    return {"ok": True, "achievement": clean(row)}


@router.post("/api/rewards/requests/{achievement_id}/reject")
def rewards_request_reject(achievement_id: str, body: RewardReviewIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.VERIFY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.review_achievement(session, achievement_id, "REJECT", body.reason)
    if not row:
        _reward_error(msg)
    return {"ok": True, "achievement": clean(row)}


@router.post("/api/rewards/awards")
def rewards_award(body: RewardAchievementIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.STAFF_AWARD_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.submit_achievement(session, body.model_dump())
    if not row:
        _reward_error(msg)
    return {"ok": True, "achievement": clean(row), "notice": msg or None}


@router.get("/api/rewards/requests")
def rewards_requests(session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.VERIFY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    pending, n1 = rewards.list_achievements(session, status="PENDING_VERIFICATION", limit=100)
    approval, n2 = rewards.list_achievements(session, status="PENDING_APPROVAL", limit=100)
    return {"pending": clean(pending), "approval": clean(approval), "total": n1 + n2}


@router.post("/api/rewards/transactions/{txn_id}/reverse")
def rewards_reverse(txn_id: str, body: RewardReverseIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.REVERSE_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.reverse_transaction(session, txn_id, body.reason)
    if not row:
        _reward_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/rewards/adjustments")
def rewards_adjust(body: RewardAdjustIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.REVERSE_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.adjust_points(session, body.student_id if body.student_id is not None else body.studentId, body.points, body.reason)
    if not row:
        _reward_error(msg)
    return {"ok": True, **clean(row)}


@router.get("/api/rewards/recommend")
def rewards_recommend(category: str, achievementType: str = "PARTICIPATION", achievementLevel: str = "INSTITUTIONAL", session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.STAFF_AWARD_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return clean(rewards.recommend(category, achievementType, achievementLevel) or {"points": None})


@router.get("/api/rewards/rules")
def rewards_rules(session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return clean(rewards.public_rules())


@router.get("/api/rewards/settings")
def rewards_settings_get(session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"settings": clean(rewards.get_settings())}


@router.put("/api/rewards/settings")
def rewards_settings_put(body: RewardSettingsIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"ok": True, "settings": clean(rewards.save_settings(body.model_dump(exclude_none=True), session))}


@router.get("/api/rewards/policies")
def rewards_policies(session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return {"policies": clean(rewards.list_policies(active_only=session.get("user_role") != "administrator"))}


@router.post("/api/rewards/policies")
def rewards_policy_save(body: RewardPolicyIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.upsert_policy(body.model_dump(), session)
    if not row:
        _reward_error(msg)
    return {"ok": True, "policy": clean(row)}


@router.get("/api/rewards/marketplace")
def rewards_marketplace(category: str = "", merchantId: str = "", q: str = "", session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return {"offers": clean(rewards.marketplace(session, category=category, merchant_id=merchantId, q=q))}


@router.get("/api/rewards/offers/{offer_id}")
def rewards_offer_one(offer_id: str, session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    rows = [row for row in rewards.marketplace(session) if str(row.get("id")) == str(offer_id)]
    if not rows:
        raise HTTPException(status_code=404, detail="NOT_FOUND")
    return {"offer": clean(rows[0])}


@router.post("/api/rewards/offers/{offer_id}/claim")
def rewards_offer_claim(offer_id: str, body: RewardClaimIn | None = None, session: dict = Depends(require_session)):
    row, msg = rewards.claim_offer(session, offer_id, (body.idempotencyKey or body.idempotency_key) if body else "")
    if not row:
        _reward_error(msg)
    return {"ok": True, "voucher": clean(row), "notice": msg or None}


@router.get("/api/rewards/vouchers")
def rewards_vouchers(status: str = "", session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return {"vouchers": clean(rewards.list_vouchers(session, status=status))}


@router.get("/api/rewards/vouchers/{voucher_id}")
def rewards_voucher_one(voucher_id: str, session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    row, msg = rewards.get_voucher(session, voucher_id)
    if not row:
        _reward_error(msg)
    return {"voucher": clean(row)}


@router.post("/api/rewards/vouchers/{voucher_id}/cancel")
def rewards_voucher_cancel(voucher_id: str, body: RewardCancelIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.cancel_voucher(session, voucher_id, body.reason, refund=body.refund)
    if not row:
        _reward_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/rewards/redemptions/validate")
def rewards_redeem_validate(body: RewardRedeemIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.REDEEM_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.validate_redemption(session, body.token)
    if not row:
        _reward_error(msg)
    return clean(row)


@router.post("/api/rewards/redemptions/confirm")
def rewards_redeem_confirm(body: RewardRedeemIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.REDEEM_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.confirm_redemption(session, body.token)
    if not row:
        _reward_error(msg)
    return {"ok": True, **clean(row)}


@router.get("/api/rewards/merchants")
def rewards_merchants(session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return {"merchants": clean(rewards.list_merchants(session, include_inactive=session.get("user_role") == "administrator"))}


@router.post("/api/rewards/merchants")
def rewards_merchant_save(body: RewardMerchantIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.MERCHANT_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.upsert_merchant(session, body.model_dump())
    if not row:
        _reward_error(msg)
    return {"ok": True, "merchant": clean(row)}


@router.post("/api/rewards/offers")
def rewards_offer_save(body: RewardOfferIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.MERCHANT_MANAGE_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    row, msg = rewards.upsert_offer(session, body.model_dump())
    if not row:
        _reward_error(msg)
    return {"ok": True, "offer": clean(row)}


@router.get("/api/rewards/analytics")
def rewards_analytics(session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES + ("teacher",):
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return clean(rewards.analytics(session))


@router.get("/api/rewards/leaderboard")
def rewards_leaderboard(session: dict = Depends(require_session)):
    _require_reward_viewer(session)
    return clean(rewards.leaderboard(session))


@router.get("/api/rewards/reconcile")
def rewards_reconcile(session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return clean(rewards.reconcile())


@router.post("/api/rewards/jobs/tick")
def rewards_tick(session: dict = Depends(require_session)):
    if session.get("user_role") not in rewards.POLICY_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return clean(rewards.tick_jobs(session))


class AttendanceSessionIn(BaseModel):
    subject_id: int | None = None
    subjectId: int | None = None
    lecture: str = ""
    duration_minutes: int | None = None
    durationMinutes: int | None = None


class AttendanceVerifyIn(BaseModel):
    session_id: str = ""
    sessionId: str = ""
    token: str = ""
    code: str = ""
    device_token: str = ""
    deviceToken: str = ""


class AttendanceCorrectIn(BaseModel):
    student_id: int | None = None
    studentId: int | None = None
    decision: str = ""
    reason: str = ""


class AttendanceSettingsIn(BaseModel):
    ai_attendance_enabled: bool | None = None
    qr_verification_enabled: bool | None = None
    secret_code_enabled: bool | None = None
    voice_verification_enabled: bool | None = None
    email_verification_enabled: bool | None = None
    device_binding_enabled: bool | None = None
    allow_image_upload: bool | None = None
    verification_mode: str | None = None
    session_duration_minutes: int | None = None
    qr_expiry_seconds: int | None = None
    code_expiry_seconds: int | None = None
    max_verification_attempts: int | None = None


class AttendanceReasonIn(BaseModel):
    reason: str = ""


def _attendance_error(msg: str):
    mapping = {
        "FEATURE_DISABLED": 403,
        "FORBIDDEN": 403,
        "UNAUTHORIZED": 401,
        "NOT_FOUND": 404,
        "RATE_LIMITED": 429,
        "SUBJECT_NOT_YOURS": 403,
        "SESSION_INACTIVE": 400,
        "TOKEN_USED": 400,
        "TOKEN_EXPIRED": 400,
        "TOKEN_INVALID": 400,
        "TOKEN_MISMATCH": 400,
        "CODE_INVALID": 400,
        "DEVICE_MISMATCH": 403,
        "ALREADY_PRESENT": 409,
        "FACE_NOT_MATCHED": 400,
        "NOT_ELIGIBLE": 403,
        "NOT_ENROLLED": 403,
        "AI_UNAVAILABLE": 503,
        "POLICY_FORBIDS_FACE_ONLY": 403,
    }
    raise HTTPException(status_code=mapping.get(msg, 400), detail=msg)


@router.post("/api/attendance/sessions")
def attendance_session_create(body: AttendanceSessionIn, session: dict = Depends(require_session)):
    row, msg = attendance.create_session(session, body.model_dump())
    if not row:
        _attendance_error(msg)
    return {"ok": True, "session": clean(row)}


@router.get("/api/attendance/sessions")
def attendance_session_list(session: dict = Depends(require_session)):
    rows, msg = attendance.list_teacher_sessions(session)
    if msg:
        _attendance_error(msg)
    return {"sessions": clean(rows)}


@router.get("/api/attendance/sessions/{public_id}")
def attendance_session_one(public_id: str, session: dict = Depends(require_session)):
    row, msg = attendance.get_session(session, public_id)
    if not row:
        _attendance_error(msg)
    return {"session": clean(row)}


@router.post("/api/attendance/sessions/{public_id}/analyze")
async def attendance_session_analyze(
    public_id: str,
    photos: list[UploadFile] = File(default=[]),
    session: dict = Depends(require_session),
):
    uploads = []
    for photo in photos:
        uploads.append({"filename": photo.filename, "bytes": await photo.read()})
    row, msg = attendance.analyze_session(session, public_id, uploads)
    if not row:
        _attendance_error(msg)
    return {"ok": True, "session": clean(row)}


@router.post("/api/attendance/sessions/{public_id}/complete")
def attendance_session_complete(public_id: str, body: AttendanceReasonIn | None = None, session: dict = Depends(require_session)):
    row, msg = attendance.complete_session(session, public_id, (body.reason if body else ""))
    if not row:
        _attendance_error(msg)
    return {"ok": True, "session": clean(row)}


@router.post("/api/attendance/sessions/{public_id}/cancel")
def attendance_session_cancel(public_id: str, body: AttendanceReasonIn, session: dict = Depends(require_session)):
    row, msg = attendance.cancel_session(session, public_id, body.reason)
    if not row:
        _attendance_error(msg)
    return {"ok": True, "session": clean(row)}


@router.post("/api/attendance/sessions/{public_id}/finalize-matched")
def attendance_finalize_matched(public_id: str, body: AttendanceReasonIn, session: dict = Depends(require_session)):
    row, msg = attendance.faculty_finalize_matched(session, public_id, body.reason)
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/attendance/sessions/{public_id}/correction")
def attendance_correction(public_id: str, body: AttendanceCorrectIn, session: dict = Depends(require_session)):
    row, msg = attendance.correct_mark(
        session,
        public_id,
        body.student_id if body.student_id is not None else body.studentId,
        body.decision,
        body.reason,
    )
    if not row:
        _attendance_error(msg)
    return {"ok": True, "session": clean(row)}


@router.get("/api/attendance/student/pending")
def attendance_student_pending(session: dict = Depends(require_session)):
    rows, msg = attendance.student_pending(session)
    if msg:
        _attendance_error(msg)
    return {"pending": clean(rows)}


@router.get("/api/attendance/student/history")
def attendance_student_history(session: dict = Depends(require_session)):
    rows, msg = attendance.student_history(session)
    if msg:
        _attendance_error(msg)
    return {"history": clean(rows)}


@router.post("/api/attendance/verification/qr")
def attendance_issue_qr(body: AttendanceVerifyIn, session: dict = Depends(require_session)):
    row, msg = attendance.issue_qr(session, body.sessionId or body.session_id)
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/attendance/verification/code")
def attendance_issue_code(body: AttendanceVerifyIn, session: dict = Depends(require_session)):
    row, msg = attendance.issue_code(session, body.sessionId or body.session_id)
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/attendance/verification/confirm")
def attendance_confirm(body: AttendanceVerifyIn, session: dict = Depends(require_session)):
    row, msg = attendance.confirm_verification(session, body.model_dump())
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/attendance/device/register")
def attendance_device_register(body: AttendanceVerifyIn | None = None, session: dict = Depends(require_session)):
    row, msg = attendance.register_device(session, (body.deviceToken or body.device_token) if body else "")
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.post("/api/attendance/sessions/{public_id}/dispute")
def attendance_dispute(public_id: str, body: AttendanceReasonIn, session: dict = Depends(require_session)):
    row, msg = attendance.create_dispute(session, public_id, body.reason)
    if not row:
        _attendance_error(msg)
    return {"ok": True, **clean(row)}


@router.get("/api/attendance/settings")
def attendance_settings_get(session: dict = Depends(require_session)):
    if session.get("user_role") not in attendance.REVIEW_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"settings": clean(attendance.get_settings()), "email": clean(attendance.email_status())}


@router.put("/api/attendance/settings")
def attendance_settings_put(body: AttendanceSettingsIn, session: dict = Depends(require_session)):
    if session.get("user_role") not in attendance.SETTINGS_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"ok": True, "settings": clean(attendance.save_settings(body.model_dump(exclude_none=True), session))}


@router.get("/api/attendance/analytics")
def attendance_analytics(session: dict = Depends(require_session)):
    row, msg = attendance.analytics(session)
    if not row:
        _attendance_error(msg)
    return clean(row)


class PredictionDocumentIn(BaseModel):
    title: str = ""
    filename: str = ""
    content: str = ""
    text: str = ""
    documentType: str = ""
    document_type: str = ""
    subject: str = ""
    year: int | None = None
    official: bool = False
    sourceUrl: str = ""
    source_url: str = ""


class PredictionPatchIn(BaseModel):
    title: str = ""
    documentType: str = ""
    document_type: str = ""
    subject: str = ""
    official: bool | None = None


class PredictionAnalyzeIn(BaseModel):
    subject: str = ""
    domain: str = "ALL"
    mode: str = "GENERAL"
    days: int | None = None
    hours: int | None = None
    hoursPerDay: int | None = None
    targetYear: int | str | None = None
    target_year: int | str | None = None
    resumeText: str = ""
    resume_text: str = ""
    jobText: str = ""
    job_text: str = ""
    weakAreas: list[str] | None = None
    strongAreas: list[str] | None = None


class PredictionQueryIn(PredictionAnalyzeIn):
    question: str = ""
    q: str = ""


class PredictionPlanIn(BaseModel):
    id: int | str | None = None
    subject: str = ""
    mode: str = "GENERAL"
    days: list | None = None
    items: list | None = None
    userModified: bool = True
    user_modified: bool = True


class PredictionOutcomeIn(BaseModel):
    actualOutcome: str = ""
    actual_outcome: str = ""
    observedAt: str = ""
    notes: str = ""


class PredictionSettingsIn(BaseModel):
    enabled: bool | None = None
    current_academic_year: str | None = None
    min_pyq_years: int | None = None
    min_schedule_years: int | None = None
    min_career_docs: int | None = None
    min_stipend_samples: int | None = None
    min_hackathon_docs: int | None = None
    similarity_threshold: float | None = None
    weights: dict | None = None


def _prediction_error(msg: str):
    mapping = {
        "FEATURE_DISABLED": 403,
        "FORBIDDEN": 403,
        "UNAUTHORIZED": 401,
        "NOT_FOUND": 404,
        "RATE_LIMITED": 429,
        "DUPLICATE": 409,
        "URL_FETCH_DISABLED": 400,
        "EMPTY_DOCUMENT": 400,
        "EMPTY_QUERY": 400,
        "SAVE_FAILED": 500,
        "PROCESSING_FAILED": 400,
    }
    if msg in mapping:
        raise HTTPException(status_code=mapping[msg], detail=msg)
    raise HTTPException(status_code=400, detail=msg or "Request failed.")


def _prediction_summary(session: dict):
    try:
        return predictions.student_summary(session)
    except Exception:
        return {"available": False}


def _community_summary(session: dict):
    try:
        return communities.student_summary(session)
    except Exception:
        return {"available": False}


def _community_error(msg: str):
    mapping = {
        "FEATURE_DISABLED": 403,
        "FORBIDDEN": 403,
        "UNAUTHORIZED": 401,
        "NOT_FOUND": 404,
        "RATE_LIMITED": 429,
        "POTENTIAL_DUPLICATE": 409,
        "COMMUNITY_SUSPENDED": 403,
        "COMMUNITY_UNAVAILABLE": 403,
        "MEMBER_SUSPENDED": 403,
        "NOT_EDITABLE": 400,
        "MEMBERSHIP_LIMIT": 400,
        "EVENT_FULL": 400,
        "EMPTY_CONTENT": 400,
        "INVALID_REQUEST": 400,
        "INVALID_DECISION": 400,
        "INVALID_CATEGORY": 400,
        "INVALID_EVENT": 400,
        "INVALID_RESOURCE": 400,
        "INVALID_REASON": 400,
        "INVALID_TARGET": 400,
        "INVALID_POLL": 400,
        "INVALID_REACTION": 400,
        "INVALID_STATUS": 400,
        "SAVE_FAILED": 500,
    }
    raise HTTPException(status_code=mapping.get(msg, 400), detail=msg or "Request failed.")


class CommunitySearchIn(BaseModel):
    q: str = ""
    search: str = ""
    category: str = ""
    mine: bool = False
    offset: int = 0
    limit: int = 20


class CommunityRequestIn(BaseModel):
    name: str = ""
    category: str = ""
    categoryCode: str = ""
    category_id: int | str | None = None
    description: str = ""
    purpose: str = ""
    reason: str = ""
    rules: str = ""
    tags: list[str] | None = None
    expectedMembers: str = ""
    bannerUrl: str = ""
    previewOnly: bool = False
    continueDespiteDuplicates: bool = False


class CommunityReviewIn(BaseModel):
    decision: str = ""
    reason: str = ""
    grantAdmin: bool = True


class CommunityPostIn(BaseModel):
    content: str = ""
    kind: str = "POST"
    link: str = ""
    options: list[str] | None = None


class CommunityCommentIn(BaseModel):
    content: str = ""


class CommunityReactIn(BaseModel):
    kind: str = ""
    reaction: str = ""
    option: int | None = None


class CommunityEventIn(BaseModel):
    title: str = ""
    description: str = ""
    startAt: str = ""
    endAt: str = ""
    location: str = ""
    capacity: int | None = None
    maxParticipants: int | None = None
    registrationDeadline: str = ""


class CommunityResourceIn(BaseModel):
    title: str = ""
    url: str = ""
    link: str = ""
    note: str = ""
    description: str = ""
    category: str = "Other"


class CommunityReportIn(BaseModel):
    communityId: int | str | None = None
    community_id: int | str | None = None
    targetType: str = "POST"
    postId: int | str | None = None
    commentId: int | str | None = None
    resourceId: int | str | None = None
    reportedStudentId: int | str | None = None
    reason: str = ""
    description: str = ""


class CommunityResolveIn(BaseModel):
    action: str = "NO_ACTION"
    reason: str = ""


class CommunityPrivacyIn(BaseModel):
    studentId: int | None = None
    showName: bool | None = None
    showPhoto: bool | None = None
    showDepartment: bool | None = None
    showSemester: bool | None = None
    showSkills: bool | None = None
    showBio: bool | None = None
    showPortfolio: bool | None = None
    displayName: str = ""
    photoUrl: str = ""
    course: str = ""
    semester: str = ""
    skills: str = ""
    bio: str = ""
    portfolio: str = ""
    notifyPref: str = ""
    interests: list[str] | None = None


class CommunityCategoryIn(BaseModel):
    id: int | str | None = None
    code: str = ""
    name: str = ""
    active: bool | None = None
    sortOrder: int | None = None


class CommunityStatusIn(BaseModel):
    status: str = ""
    reason: str = ""


class CommunityRoleIn(BaseModel):
    studentId: int | str | None = None
    role: str = "MEMBER"


@router.get("/api/communities/overview")
def communities_overview(session: dict = Depends(require_session)):
    row, msg = communities.overview(session)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities")
def communities_list(q: str = "", category: str = "", mine: bool = False, offset: int = 0, limit: int = 20, session: dict = Depends(require_session)):
    row, msg = communities.list_communities(session, {"q": q, "category": category, "mine": mine, "offset": offset, "limit": limit})
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/categories")
def communities_categories(session: dict = Depends(require_session)):
    rows, msg = communities.list_categories(session)
    if rows is None:
        _community_error(msg)
    return {"categories": clean(rows)}


@router.post("/api/communities/categories")
def communities_category_save(body: CommunityCategoryIn, session: dict = Depends(require_session)):
    row, msg = communities.save_category(session, body.model_dump())
    if not row:
        _community_error(msg)
    return clean({"ok": True, **row})


@router.get("/api/communities/privacy")
def communities_privacy_get(session: dict = Depends(require_session)):
    row, msg = communities.get_privacy(session)
    if not row:
        _community_error(msg)
    return clean(row)


@router.put("/api/communities/privacy")
def communities_privacy_put(body: CommunityPrivacyIn, session: dict = Depends(require_session)):
    row, msg = communities.save_privacy(session, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/feed")
def communities_feed(offset: int = 0, limit: int = 20, session: dict = Depends(require_session)):
    row, msg = communities.feed(session, offset=offset, limit=limit)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/recommended")
def communities_recommended(session: dict = Depends(require_session)):
    row, msg = communities.recommend(session)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/similar")
def communities_similar(body: CommunityRequestIn, session: dict = Depends(require_session)):
    row, msg = communities.similar_communities(session, body.model_dump())
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/requests")
def communities_requests(session: dict = Depends(require_session)):
    rows, msg = communities.list_requests(session)
    if rows is None:
        _community_error(msg)
    return {"requests": clean(rows)}


@router.post("/api/communities/requests")
def communities_request_create(body: CommunityRequestIn, session: dict = Depends(require_session)):
    row, msg = communities.create_request(session, body.model_dump())
    if row is None:
        _community_error(msg)
    if msg == "POTENTIAL_DUPLICATE":
        return clean({"ok": False, **row})
    return clean({"ok": True, **row})


@router.patch("/api/communities/requests/{request_id}")
def communities_request_update(request_id: str, body: CommunityRequestIn, session: dict = Depends(require_session)):
    row, msg = communities.update_request(session, request_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean({"ok": True, **row})


@router.post("/api/communities/requests/{request_id}/review")
def communities_request_review(request_id: str, body: CommunityReviewIn, session: dict = Depends(require_session)):
    row, msg = communities.review_request(session, request_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/community-reports")
def communities_reports(communityId: str = "", session: dict = Depends(require_session)):
    rows, msg = communities.list_reports(session, communityId or None)
    if rows is None:
        _community_error(msg)
    return {"reports": clean(rows)}


@router.get("/api/communities/{community_id}")
def communities_get(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.get_community(session, community_id)
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/join")
def communities_join(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.join(session, community_id)
    if not row:
        _community_error(msg)
    return clean(row)


@router.delete("/api/communities/{community_id}/leave")
def communities_leave(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.leave(session, community_id)
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/members")
def communities_members(community_id: str, offset: int = 0, limit: int = 20, session: dict = Depends(require_session)):
    row, msg = communities.list_members(session, community_id, offset=offset, limit=limit)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/posts")
def communities_posts(community_id: str, offset: int = 0, limit: int = 20, kind: str = "", session: dict = Depends(require_session)):
    row, msg = communities.list_posts(session, community_id, offset=offset, limit=limit, kind=kind)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/posts")
def communities_post_create(community_id: str, body: CommunityPostIn, session: dict = Depends(require_session)):
    row, msg = communities.create_post(session, community_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/posts/{post_id}/comments")
def communities_comments(community_id: str, post_id: str, offset: int = 0, limit: int = 30, session: dict = Depends(require_session)):
    row, msg = communities.list_comments(session, community_id, post_id, offset=offset, limit=limit)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/posts/{post_id}/comments")
def communities_comment_create(community_id: str, post_id: str, body: CommunityCommentIn, session: dict = Depends(require_session)):
    row, msg = communities.add_comment(session, community_id, post_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/posts/{post_id}/reactions")
def communities_react(community_id: str, post_id: str, body: CommunityReactIn, session: dict = Depends(require_session)):
    row, msg = communities.react(session, community_id, post_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.delete("/api/communities/{community_id}/posts/{post_id}")
def communities_post_remove(community_id: str, post_id: str, session: dict = Depends(require_session)):
    row, msg = communities.remove_post(session, community_id, post_id)
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/events")
def communities_events(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.list_events(session, community_id)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/events")
def communities_event_create(community_id: str, body: CommunityEventIn, session: dict = Depends(require_session)):
    row, msg = communities.create_event(session, community_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/events/{event_id}/register")
def communities_event_register(community_id: str, event_id: str, session: dict = Depends(require_session)):
    row, msg = communities.register_event(session, community_id, event_id, cancel=False)
    if not row:
        _community_error(msg)
    return clean(row)


@router.delete("/api/communities/{community_id}/events/{event_id}/register")
def communities_event_cancel(community_id: str, event_id: str, session: dict = Depends(require_session)):
    row, msg = communities.register_event(session, community_id, event_id, cancel=True)
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/resources")
def communities_resources(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.list_resources(session, community_id)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/resources")
def communities_resource_create(community_id: str, body: CommunityResourceIn, session: dict = Depends(require_session)):
    row, msg = communities.add_resource(session, community_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/reports")
def communities_report(body: CommunityReportIn, session: dict = Depends(require_session)):
    row, msg = communities.create_report(session, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/reports/{report_id}/resolve")
def communities_report_resolve(report_id: str, body: CommunityResolveIn, session: dict = Depends(require_session)):
    row, msg = communities.resolve_report(session, report_id, body.model_dump())
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/status")
def communities_status(community_id: str, body: CommunityStatusIn, session: dict = Depends(require_session)):
    row, msg = communities.set_community_status(session, community_id, body.status, body.reason)
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/{community_id}/roles")
def communities_roles(community_id: str, body: CommunityRoleIn, session: dict = Depends(require_session)):
    row, msg = communities.set_member_role(session, community_id, body.studentId, body.role)
    if not row:
        _community_error(msg)
    return clean(row)


@router.post("/api/communities/block/{student_id}")
def communities_block(student_id: str, session: dict = Depends(require_session)):
    row, msg = communities.block_student(session, student_id)
    if not row:
        _community_error(msg)
    return clean(row)


@router.get("/api/communities/{community_id}/analytics")
def communities_analytics(community_id: str, session: dict = Depends(require_session)):
    row, msg = communities.analytics(session, community_id)
    if row is None:
        _community_error(msg)
    return clean(row)


@router.get("/api/predictions/overview")
def predictions_overview(session: dict = Depends(require_session)):
    row, msg = predictions.overview(session)
    if row is None:
        _prediction_error(msg)
    return clean(row)


@router.get("/api/predictions/documents")
def predictions_documents(session: dict = Depends(require_session)):
    if session.get("user_role") not in predictions.VIEW_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"documents": clean(predictions.visible_documents(session))}


@router.get("/api/predictions/documents/{doc_id}")
def predictions_document_get(doc_id: str, session: dict = Depends(require_session)):
    row, msg = predictions.get_document(session, doc_id, include_text=True)
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.post("/api/predictions/documents")
def predictions_document_create(body: PredictionDocumentIn, session: dict = Depends(require_session)):
    row, msg = predictions.ingest_text(session, body.model_dump())
    if not row:
        _prediction_error(msg)
    if msg == "DUPLICATE":
        return clean({"ok": True, "duplicate": True, **row})
    if msg:
        return clean({"ok": False, "error": msg, **row})
    return clean({"ok": True, **row})


@router.post("/api/predictions/documents/upload")
async def predictions_document_upload(
    file: UploadFile = File(...),
    title: str = Form(""),
    documentType: str = Form(""),
    subject: str = Form(""),
    official: str = Form("false"),
    session: dict = Depends(require_session),
):
    data = await file.read()
    row, msg = predictions.ingest_file(session, file.filename, data, {
        "title": title,
        "documentType": documentType,
        "subject": subject,
        "official": str(official).lower() in {"1", "true", "yes"},
    })
    if not row:
        _prediction_error(msg)
    if msg == "DUPLICATE":
        return clean({"ok": True, "duplicate": True, **row})
    if msg:
        return clean({"ok": False, "error": msg, **row})
    return clean({"ok": True, **row})


@router.patch("/api/predictions/documents/{doc_id}")
def predictions_document_patch(doc_id: str, body: PredictionPatchIn, session: dict = Depends(require_session)):
    row, msg = predictions.update_document(session, doc_id, body.model_dump(exclude_none=True))
    if not row:
        _prediction_error(msg)
    return clean({"ok": True, **row})


@router.delete("/api/predictions/documents/{doc_id}")
def predictions_document_delete(doc_id: str, session: dict = Depends(require_session)):
    row, msg = predictions.delete_document(session, doc_id)
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.post("/api/predictions/documents/{doc_id}/reprocess")
def predictions_document_reprocess(doc_id: str, session: dict = Depends(require_session)):
    row, msg = predictions.reprocess(session, doc_id)
    if not row:
        _prediction_error(msg)
    return clean({"ok": True, **row})


@router.post("/api/predictions/analyze")
def predictions_analyze(body: PredictionAnalyzeIn | None = None, session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, (body.model_dump() if body else {}))
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.get("/api/predictions/academic")
def predictions_academic(subject: str = "", mode: str = "GENERAL", session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, {"subject": subject, "mode": mode, "domain": "ACADEMIC"})
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.get("/api/predictions/exam-date")
def predictions_exam_date(subject: str = "", targetYear: str = "", session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, {"subject": subject, "domain": "INSTITUTIONAL", "targetYear": targetYear})
    if not row:
        _prediction_error(msg)
    return clean({"examDate": row.get("examDate"), "disclaimer": row.get("disclaimer")})


@router.get("/api/predictions/questions")
def predictions_questions(subject: str = "", mode: str = "GENERAL", session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, {"subject": subject, "mode": mode, "domain": "ACADEMIC"})
    if not row:
        _prediction_error(msg)
    academic = row.get("academic") or {}
    return clean({"questions": academic.get("questions") or [], "status": academic.get("status"), "insufficientReason": academic.get("insufficientReason"), "disclaimer": academic.get("disclaimer")})


@router.get("/api/predictions/topics")
def predictions_topics(subject: str = "", mode: str = "GENERAL", session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, {"subject": subject, "mode": mode, "domain": "ACADEMIC"})
    if not row:
        _prediction_error(msg)
    academic = row.get("academic") or {}
    return clean({"topics": academic.get("topics") or [], "status": academic.get("status"), "disclaimer": academic.get("disclaimer")})


@router.get("/api/predictions/career")
def predictions_career(mode: str = "GENERAL", session: dict = Depends(require_session)):
    row, msg = predictions.analyze(session, {"mode": mode, "domain": "CAREER"})
    if not row:
        _prediction_error(msg)
    return clean(row.get("career") or {})


@router.post("/api/predictions/query")
def predictions_query(body: PredictionQueryIn, session: dict = Depends(require_session)):
    row, msg = predictions.query(session, body.model_dump())
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.get("/api/predictions/history")
def predictions_history(limit: int = 30, session: dict = Depends(require_session)):
    rows, msg = predictions.list_history(session, limit=limit)
    if rows is None:
        _prediction_error(msg)
    return {"history": clean(rows)}


@router.get("/api/predictions/evidence/{result_id}")
def predictions_evidence(result_id: str, session: dict = Depends(require_session)):
    rows, msg = predictions.evidence_for(session, result_id)
    if rows is None:
        _prediction_error(msg)
    return {"evidence": clean(rows)}


@router.post("/api/predictions/history/{history_id}/outcome")
def predictions_outcome(history_id: str, body: PredictionOutcomeIn, session: dict = Depends(require_session)):
    row, msg = predictions.record_outcome(session, history_id, body.model_dump())
    if not row:
        _prediction_error(msg)
    return clean({"ok": True, **row})


@router.get("/api/predictions/plans")
def predictions_plans(session: dict = Depends(require_session)):
    rows, msg = predictions.list_plans(session)
    if rows is None:
        _prediction_error(msg)
    return {"plans": clean(rows)}


@router.post("/api/predictions/plans")
def predictions_plans_save(body: PredictionPlanIn, session: dict = Depends(require_session)):
    row, msg = predictions.save_plan(session, body.model_dump())
    if not row:
        _prediction_error(msg)
    return clean(row)


@router.get("/api/predictions/settings")
def predictions_settings_get(session: dict = Depends(require_session)):
    if session.get("user_role") not in predictions.SETTINGS_ROLES:
        raise HTTPException(status_code=403, detail="FORBIDDEN")
    return {"settings": clean(predictions.get_settings())}


@router.put("/api/predictions/settings")
def predictions_settings_put(body: PredictionSettingsIn, session: dict = Depends(require_session)):
    row, msg = predictions.save_settings(body.model_dump(exclude_none=True), session)
    if not row:
        _prediction_error(msg)
    return {"ok": True, "settings": clean(row)}
