import secrets
from datetime import datetime, timedelta, timezone

from src.database.config import supabase, is_supabase_configured
from src.database.db import check_pass, hash_pass, check_teacher_exists, create_teacher, _supabase_once


def _configured() -> bool:
    return is_supabase_configured()


def log_auth_event(username, role, event, status="ok"):
    if not _configured():
        from src.database import local_store as local
        return local.log_auth_event(username, role, event, status)
    try:
        supabase.table("auth_events").insert({
            "username": username,
            "role": role,
            "event": event,
            "status": status,
        }).execute()
    except Exception:
        return None


def get_login_history(limit: int = 20, offset: int = 0, event: str | None = None):
    from src.auth.guards import require_teacher
    if not require_teacher():
        return []
    if not _configured():
        from src.database import local_store as local
        return local.get_login_history(limit=limit, offset=offset, event=event)
    try:
        query = (
            supabase.table("auth_events")
            .select("username, role, event, status, created_at")
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
        )
        if event:
            query = query.eq("event", event)
        res = query.execute()
        return res.data or []
    except Exception:
        return []


def password_strength(password: str) -> tuple[bool, str]:
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters."
    if password.strip() != password:
        return False, "Password cannot start or end with spaces."
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    if not (has_letter and has_digit):
        return False, "Password must include at least one letter and one number."
    return True, "ok"


def update_teacher_password(teacher_id, new_password):
    if not _configured():
        return False
    try:
        supabase.table("teachers").update({
            "password": hash_pass(new_password)
        }).eq("teacher_id", teacher_id).execute()
        return True
    except Exception:
        return False


def change_teacher_password(teacher_id, current_password, new_password, confirm_password, session_state=None):
    from src.auth.guards import require_same_teacher
    if not require_same_teacher(teacher_id, session_state):
        return False, "You are not allowed to change this password."
    ok, msg = password_strength(new_password)
    if not ok:
        return False, msg
    if new_password != confirm_password:
        return False, "New passwords do not match."
    try:
        res = supabase.table("teachers").select("teacher_id, username, password").eq(
            "teacher_id", teacher_id
        ).execute()
    except Exception:
        return False, "Unable to verify the current password."
    if not res.data:
        return False, "Unable to verify the current password."
    teacher = res.data[0]
    if not check_pass(current_password, teacher["password"]):
        log_auth_event(teacher.get("username"), "teacher", "password_change", "denied")
        return False, "Current password is incorrect."
    if not update_teacher_password(teacher_id, new_password):
        return False, "Could not update password."
    log_auth_event(teacher.get("username"), "teacher", "password_change", "ok")
    return True, "Password updated."


def reset_teacher_password(username, registered_name, new_password, confirm_password):
    """Identity check uses existing teacher name + username. Same error if no match."""
    generic = "If this account exists, the password can be reset with the registered name."
    ok, msg = password_strength(new_password)
    if not ok:
        return False, msg
    if new_password != confirm_password:
        return False, "New passwords do not match."
    if not username or not registered_name:
        return False, generic
    try:
        res = supabase.table("teachers").select("teacher_id, username, name").eq(
            "username", username.strip()
        ).execute()
    except Exception:
        return False, generic
    if not res.data:
        log_auth_event(username, "teacher", "password_reset", "denied")
        return False, generic
    teacher = res.data[0]
    if str(teacher.get("name", "")).strip().lower() != registered_name.strip().lower():
        log_auth_event(username, "teacher", "password_reset", "denied")
        return False, generic
    if not update_teacher_password(teacher["teacher_id"], new_password):
        return False, generic
    log_auth_event(username, "teacher", "password_reset", "ok")
    return True, "Password reset. You can log in with the new password."


def create_teacher_invite(invited_name, invited_username, invited_by, session_state=None):
    from src.auth.guards import require_same_teacher
    if not require_same_teacher(invited_by, session_state):
        return None, "You are not allowed to create invitations."
    if not invited_name or not invited_username:
        return None, "Name and username are required."
    if check_teacher_exists(invited_username):
        return None, "That username is already registered."
    try:
        existing = _supabase_once(lambda: (
            supabase.table("teacher_invites")
            .select("invite_id, used_at")
            .eq("invited_username", invited_username)
            .is_("used_at", "null")
            .execute()
        ))
        if existing.data:
            return None, "An unused invitation already exists for this username."
    except Exception as exc:
        err = str(exc)
        return None, f"Invitation storage is not available. {err.splitlines()[0][:160]}"

    token = secrets.token_urlsafe(16)
    try:
        _supabase_once(lambda: supabase.table("teacher_invites").insert({
            "invited_name": invited_name.strip(),
            "invited_username": invited_username.strip(),
            "token_hash": hash_pass(token),
            "invited_by": invited_by,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
        }).execute())
    except Exception as exc:
        err = str(exc)
        if "duplicate" in err.lower() or "unique" in err.lower():
            return None, "An unused invitation already exists for this username."
        return None, f"Invitation storage is not available. {err.splitlines()[0][:160]}"
    log_auth_event(invited_username, "teacher", "invite_created", "ok")
    return token, "Invitation created. Share the activation code with the faculty member."


def list_teacher_invites(invited_by, session_state=None):
    from src.auth.guards import require_same_teacher
    if not require_same_teacher(invited_by, session_state):
        return []
    try:
        res = (
            supabase.table("teacher_invites")
            .select("invite_id, invited_name, invited_username, expires_at, used_at, created_at")
            .eq("invited_by", invited_by)
            .order("created_at", desc=True)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


def activate_teacher_invite(username, token, password, confirm_password):
    ok, msg = password_strength(password)
    if not ok:
        return False, msg
    if password != confirm_password:
        return False, "Passwords do not match."
    if not username or not token:
        return False, "Activation code and username are required."
    try:
        res = (
            supabase.table("teacher_invites")
            .select("*")
            .eq("invited_username", username.strip())
            .is_("used_at", "null")
            .execute()
        )
    except Exception:
        return False, "Invitation storage is not available."
    if not res.data:
        return False, "This invitation is invalid or already used."

    invite = None
    for row in res.data:
        if check_pass(token, row["token_hash"]):
            invite = row
            break
    if not invite:
        return False, "This invitation is invalid or already used."

    expires = invite.get("expires_at")
    if expires:
        try:
            exp = datetime.fromisoformat(str(expires).replace("Z", "+00:00"))
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) > exp:
                return False, "This invitation has expired."
        except ValueError:
            pass

    if check_teacher_exists(invite["invited_username"]):
        return False, "That username is already registered."

    created = create_teacher(invite["invited_username"], password, invite["invited_name"])
    if not created:
        return False, "Could not activate the account."

    try:
        supabase.table("teacher_invites").update({
            "used_at": datetime.now(timezone.utc).isoformat()
        }).eq("invite_id", invite["invite_id"]).execute()
    except Exception:
        pass
    log_auth_event(invite["invited_username"], "teacher", "account_activated", "ok")
    return True, "Account activated. You can log in now."
