"""File-backed classroom store used when Supabase is not configured."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from src.database.db import check_pass, hash_pass

_LOCK = threading.Lock()
_PATH = Path(__file__).resolve().parents[2] / "data" / "local_db.json"

_EMPTY = {
    "teachers": [],
    "students": [],
    "subjects": [],
    "subject_students": [],
    "attendance_logs": [],
    "staff_users": [],
    "teacher_invites": [],
    "auth_events": [],
    "seq": {
        "teachers": 1,
        "students": 1,
        "subjects": 1,
        "subject_students": 1,
        "attendance_logs": 1,
        "staff_users": 1,
        "teacher_invites": 1,
        "auth_events": 1,
    },
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load():
    if not _PATH.exists():
        data = deepcopy(_EMPTY)
        _seed(data)
        _dump(data)
        return data
    with _PATH.open(encoding="utf-8") as handle:
        return json.load(handle)


def _dump(data):
    _PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(_PATH)


def _next_id(data, table):
    value = int(data["seq"].get(table, 1))
    data["seq"][table] = value + 1
    return value


def _seed(data):
    return


def with_db(fn):
    with _LOCK:
        data = _load()
        result = fn(data)
        _dump(data)
        return result


def read_db():
    with _LOCK:
        return _load()


def public_teacher(row):
    if not row:
        return None
    out = dict(row)
    out.pop("password", None)
    return out


def public_student(row):
    if not row:
        return None
    out = dict(row)
    out.pop("password", None)
    return out


def public_staff(row):
    if not row:
        return None
    out = dict(row)
    out.pop("password", None)
    return out


def teacher_login(username, password):
    for row in read_db()["teachers"]:
        if row.get("username") == username and check_pass(password, row.get("password") or ""):
            return public_teacher(row)
    return None


def teacher_exists(username):
    return any(row.get("username") == username for row in read_db()["teachers"])


def create_teacher(username, password, name):
    def _op(data):
        if any(row.get("username") == username for row in data["teachers"]):
            return None
        row = {
            "teacher_id": _next_id(data, "teachers"),
            "username": username,
            "password": hash_pass(password),
            "name": name,
            "created_at": _now(),
        }
        data["teachers"].append(row)
        return public_teacher(row)

    return with_db(_op)


def staff_login(username, password):
    for row in read_db()["staff_users"]:
        if row.get("username") == username and check_pass(password, row.get("password") or ""):
            return public_staff(row)
    return None


def create_staff(username, password, name, role):
    def _op(data):
        if any(row.get("username") == username for row in data["staff_users"]):
            return None
        row = {
            "staff_id": _next_id(data, "staff_users"),
            "username": username,
            "password": hash_pass(password),
            "name": name,
            "role": role,
            "created_at": _now(),
        }
        data["staff_users"].append(row)
        return public_staff(row)

    return with_db(_op)


def list_students():
    return [public_student(row) for row in read_db()["students"]]


def get_student(student_id):
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return None
    for row in read_db()["students"]:
        if int(row.get("student_id")) == student_id:
            return row
    return None


def create_student(name, face_embedding=None, voice_embedding=None):
    def _op(data):
        row = {
            "student_id": _next_id(data, "students"),
            "name": name,
            "face_embedding": face_embedding,
            "voice_embedding": voice_embedding,
            "created_at": _now(),
        }
        data["students"].append(row)
        return public_student(row)

    return with_db(_op)


def update_student_voice(student_id, voice_embedding):
    def _op(data):
        for row in data["students"]:
            if int(row.get("student_id")) == int(student_id):
                row["voice_embedding"] = voice_embedding
                return public_student(row)
        return None

    return with_db(_op)


def teacher_subjects(teacher_id):
    teacher_id = int(teacher_id)
    data = read_db()
    out = []
    for sub in data["subjects"]:
        if int(sub.get("teacher_id")) != teacher_id:
            continue
        sid = sub["subject_id"]
        enrolled = [row for row in data["subject_students"] if int(row["subject_id"]) == int(sid)]
        logs = [row for row in data["attendance_logs"] if int(row.get("subject_id") or 0) == int(sid)]
        item = dict(sub)
        item["total_students"] = len(enrolled)
        item["total_classes"] = len({row.get("timestamp") for row in logs})
        out.append(item)
    return out


def create_subject(subject_code, name, section, teacher_id):
    def _op(data):
        if any(row.get("subject_code") == subject_code for row in data["subjects"]):
            return None
        row = {
            "subject_id": _next_id(data, "subjects"),
            "subject_code": subject_code,
            "name": name,
            "section": section,
            "teacher_id": int(teacher_id),
            "created_at": _now(),
        }
        data["subjects"].append(row)
        return row

    return with_db(_op)


def subject_by_code(code):
    for row in read_db()["subjects"]:
        if str(row.get("subject_code", "")).lower() == str(code).lower():
            return row
    return None


def enroll(student_id, subject_id):
    def _op(data):
        for row in data["subject_students"]:
            if int(row["student_id"]) == int(student_id) and int(row["subject_id"]) == int(subject_id):
                return {"already": True, "row": row}
        row = {
            "id": _next_id(data, "subject_students"),
            "student_id": int(student_id),
            "subject_id": int(subject_id),
            "created_at": _now(),
        }
        data["subject_students"].append(row)
        return {"already": False, "row": row}

    return with_db(_op)


def unenroll(student_id, subject_id):
    def _op(data):
        data["subject_students"] = [
            row for row in data["subject_students"]
            if not (int(row["student_id"]) == int(student_id) and int(row["subject_id"]) == int(subject_id))
        ]
        return True

    return with_db(_op)


def student_subjects(student_id):
    data = read_db()
    subjects = {int(row["subject_id"]): row for row in data["subjects"]}
    out = []
    for row in data["subject_students"]:
        if int(row["student_id"]) != int(student_id):
            continue
        sub = subjects.get(int(row["subject_id"]))
        if sub:
            out.append({**row, "subjects": sub})
    return out


def student_attendance(student_id):
    return [row for row in read_db()["attendance_logs"] if int(row.get("student_id")) == int(student_id)]


def teacher_attendance(teacher_id):
    data = read_db()
    owned = {int(row["subject_id"]) for row in data["subjects"] if int(row["teacher_id"]) == int(teacher_id)}
    out = []
    for row in data["attendance_logs"]:
        if int(row.get("subject_id") or 0) in owned:
            sub = next((s for s in data["subjects"] if int(s["subject_id"]) == int(row["subject_id"])), None)
            item = dict(row)
            item["subjects"] = sub
            out.append(item)
    return out


def add_attendance(logs):
    def _op(data):
        saved = []
        for log in logs:
            row = dict(log)
            row["id"] = _next_id(data, "attendance_logs")
            row.setdefault("timestamp", _now())
            data["attendance_logs"].append(row)
            saved.append(row)
        return saved

    return with_db(_op)


def students_for_subject(subject_id):
    data = read_db()
    ids = {int(row["student_id"]) for row in data["subject_students"] if int(row["subject_id"]) == int(subject_id)}
    return [row for row in data["students"] if int(row["student_id"]) in ids]


def change_teacher_password(teacher_id, current_password, new_password, confirm_password):
    from src.database.auth_db import password_strength

    ok, msg = password_strength(new_password)
    if not ok:
        return False, msg
    if new_password != confirm_password:
        return False, "New passwords do not match."

    def _op(data):
        for row in data["teachers"]:
            if int(row["teacher_id"]) != int(teacher_id):
                continue
            if not check_pass(current_password, row.get("password") or ""):
                return False, "Current password is incorrect."
            row["password"] = hash_pass(new_password)
            return True, "Password updated."
        return False, "Teacher not found."

    return with_db(_op)


def reset_teacher_password(username, registered_name, new_password, confirm_password):
    from src.database.auth_db import password_strength

    generic = "If this account exists, the password can be reset with the registered name."
    ok, msg = password_strength(new_password)
    if not ok:
        return False, msg
    if new_password != confirm_password:
        return False, "New passwords do not match."

    def _op(data):
        for row in data["teachers"]:
            if row.get("username") != username:
                continue
            if str(row.get("name", "")).strip().lower() != str(registered_name).strip().lower():
                return False, generic
            row["password"] = hash_pass(new_password)
            return True, "Password reset. You can log in with the new password."
        return False, generic

    return with_db(_op)


def create_teacher_invite(invited_name, invited_username, invited_by):
    import secrets
    from datetime import timedelta

    if teacher_exists(invited_username):
        return None, "That username is already registered."
    token = secrets.token_urlsafe(16)

    def _op(data):
        data.setdefault("teacher_invites", [])
        data["seq"].setdefault("teacher_invites", 1)
        row = {
            "invite_id": _next_id(data, "teacher_invites"),
            "invited_name": invited_name,
            "invited_username": invited_username,
            "token_hash": hash_pass(token),
            "invited_by": int(invited_by),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
            "used_at": None,
            "created_at": _now(),
        }
        data["teacher_invites"].append(row)
        return row

    with_db(_op)
    return token, "Invitation created. Share the activation code with the teacher."


def list_teacher_invites(invited_by):
    rows = read_db().get("teacher_invites") or []
    return [row for row in rows if int(row.get("invited_by") or 0) == int(invited_by)]


def activate_teacher_invite(username, token, password, confirm_password):
    from src.database.auth_db import password_strength

    ok, msg = password_strength(password)
    if not ok:
        return False, msg
    if password != confirm_password:
        return False, "Passwords do not match."

    def _op(data):
        data.setdefault("teacher_invites", [])
        invite = None
        for row in data["teacher_invites"]:
            if row.get("invited_username") == username and not row.get("used_at") and check_pass(token, row.get("token_hash") or ""):
                invite = row
                break
        if not invite:
            return False, "This invitation is invalid or already used."
        teacher = {
            "teacher_id": _next_id(data, "teachers"),
            "username": username,
            "password": hash_pass(password),
            "name": invite.get("invited_name") or username,
            "created_at": _now(),
        }
        data["teachers"].append(teacher)
        invite["used_at"] = _now()
        return True, "Account activated. You can log in now."

    return with_db(_op)


def log_auth_event(username, role, event, status="ok"):
    def _op(data):
        data.setdefault("auth_events", [])
        data["seq"].setdefault("auth_events", 1)
        row = {
            "id": _next_id(data, "auth_events"),
            "username": username,
            "role": role,
            "event": event,
            "status": status,
            "created_at": _now(),
        }
        data["auth_events"].append(row)
        return row

    return with_db(_op)


def get_login_history(limit: int = 20, offset: int = 0, event: str | None = None):
    rows = list(read_db().get("auth_events") or [])
    rows.sort(key=lambda row: row.get("created_at") or "", reverse=True)
    if event:
        rows = [row for row in rows if row.get("event") == event]
    return rows[offset:offset + limit]
