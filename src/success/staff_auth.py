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
        err = store.last_error("staff_users")
        if err and "duplicate" in err.lower():
            return None, "Username already taken."
        if err:
            return None, "Could not create the staff account. Confirm staff_users is writable."
        return None, "Staff directory is unavailable. Run supabase/schema_success.sql."
    return data, "Staff account created."


def invite_staff(name, username, role, invited_by):
    if role not in STAFF_ROLES:
        return None, "Invalid role."
    name = (name or "").strip()
    username = (username or "").strip()
    if not name or not username:
        return None, "Name and username are required."
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


def list_staff_invites():
    rows = []
    for row in store.select("staff_invites") or []:
        safe = dict(row)
        safe.pop("token_hash", None)
        rows.append(safe)
    rows.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return rows


def activate_staff(username, token, password, confirm_password):
    ok, msg = password_strength(password)
    if not ok:
        return None, msg
    if password != confirm_password:
        return None, "Passwords do not match."
    username = (username or "").strip()
    token = (token or "").strip()
    if not username or not token:
        return None, "Username and invitation code are required."
    now = datetime.now(timezone.utc)
    match = None
    used_match = None
    expired_match = None
    for inv in store.select("staff_invites") or []:
        if str(inv.get("invited_username") or "").strip().lower() != username.lower():
            continue
        if not check_pass(token, inv.get("token_hash") or ""):
            continue
        if inv.get("used_at"):
            used_match = inv
            continue
        exp = inv.get("expires_at")
        parsed = None
        try:
            parsed = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except Exception:
            parsed = None
        if parsed is None or parsed < now:
            expired_match = inv
            continue
        match = inv
        break
    if not match:
        if used_match:
            return None, "This invitation has already been used."
        if expired_match:
            return None, "This invitation has expired."
        return None, "Invalid or expired invitation."
    name = match.get("invited_name") or username
    role = match.get("assigned_role")
    from src.database.config import is_supabase_configured
    if is_supabase_configured():
        data, create_msg = create_staff(username, password, name, role)
        if not data:
            return None, create_msg
        staff = data[0] if isinstance(data, list) else data
    else:
        from src.database import local_store as local
        staff = local.create_staff(username, password, name, role)
        if not staff:
            return None, "Username already taken."
    key = "invite_id" if match.get("invite_id") is not None else "id"
    store.update("staff_invites", {key: match.get(key)}, {"used_at": now.isoformat()})
    log_auth_event(username, (staff or {}).get("role"), "invite_activated", "ok")
    return staff, "Staff account activated. You can log in now."
