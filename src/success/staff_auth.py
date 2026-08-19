import secrets
from datetime import datetime, timedelta, timezone

from src.database.db import check_pass, hash_pass
from src.database.auth_db import password_strength, log_auth_event
from src.success import store


STAFF_ROLES = ("administrator", "counsellor", "faculty", "mentor")


def get_staff_public(staff_id):
    if staff_id is None:
        return None
    try:
        staff_id = int(staff_id)
    except (TypeError, ValueError):
        return None
    rows = store.select("staff_users")
    for row in rows:
        if int(row.get("staff_id") or -1) == staff_id:
            safe = dict(row)
            safe.pop("password", None)
            return safe
    return None


def staff_login(username, password):
    rows = store.select("staff_users")
    for row in rows:
        if row.get("username") == username and check_pass(password, row.get("password") or ""):
            safe = dict(row)
            safe.pop("password", None)
            return safe
    log_auth_event(username, "staff", "login_failure", "denied")
    return None


def create_staff(username, password, name, role):
    ok, msg = password_strength(password)
    if not ok:
        return None, msg
    if role not in STAFF_ROLES:
        return None, "Invalid role."
    existing = store.select("staff_users")
    if any(r.get("username") == username for r in existing):
        return None, "Username already taken."
    data = store.insert("staff_users", {
        "username": username,
        "password": hash_pass(password),
        "name": name,
        "role": role,
    })
    if not data:
        return None, "Staff directory is unavailable. Run supabase/schema_success.sql."
    return data, "Staff account created."


def invite_staff(name, username, role, invited_by):
    if role not in STAFF_ROLES:
        return None, "Invalid role."
    token = secrets.token_urlsafe(16)
    row = store.insert("staff_invites", {
        "invited_name": name,
        "invited_username": username,
        "assigned_role": role,
        "token_hash": hash_pass(token),
        "invited_by": invited_by,
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
    })
    if not row:
        return None, "Invitation storage unavailable. Run supabase/schema_success.sql."
    log_auth_event(username, role, "invite_created", "ok")
    return token, "Share this one-time code. It expires in 7 days."
