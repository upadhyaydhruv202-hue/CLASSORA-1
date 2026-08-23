"""Session helpers. No Streamlit — used by the FastAPI auth layer."""

from datetime import datetime, timedelta

from src.database.auth_db import log_auth_event

SESSION_MINUTES = 60


def _public(row: dict | None, drop=("password", "face_embedding", "voice_embedding")):
    if not row:
        return None
    safe = dict(row)
    for key in drop:
        safe.pop(key, None)
    return safe


def sanitize_teacher(teacher):
    return _public(teacher, drop=("password",))


def sanitize_student(student):
    return _public(student)


def sanitize_staff(staff):
    return _public(staff, drop=("password",))


def sanitize_merchant(merchant):
    return _public(merchant, drop=("access_code_hash", "password"))


def session_payload(*, role, teacher=None, student=None, staff=None, merchant=None, demo=False, demo_scenario=None):
    now = datetime.utcnow()
    return {
        "is_logged_in": True,
        "user_role": role,
        "login_type": "demo" if demo else role,
        "demo_mode": bool(demo),
        "demo_scenario": demo_scenario or ("multiple" if demo else None),
        "teacher_data": sanitize_teacher(teacher),
        "student_data": sanitize_student(student),
        "staff_data": sanitize_staff(staff),
        "merchant_data": sanitize_merchant(merchant),
        "last_activity": now.isoformat(),
        "session_started_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=SESSION_MINUTES)).isoformat(),
    }


def mark_login(username, role):
    log_auth_event(username, role, "login_success", "ok")
