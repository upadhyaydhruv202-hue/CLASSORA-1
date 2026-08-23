"""Secure attendance orchestration. Face identifies; the server confirms presence."""

from __future__ import annotations

import hashlib
import hmac
import io
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from src.attendance import policy as P
from src.database.config import is_supabase_configured
from src.success import notify as notifier
from src.success import store

logger = logging.getLogger("classora.attendance")

_TX = threading.Lock()
_RATES = defaultdict(deque)
_RATE_WINDOW = 900
_RATE_LIMITS = {
    "create": 20,
    "verify": 20,
    "code": 8,
    "qr": 30,
    "analyze": 20,
}

MAX_IMAGE_BYTES = 8 * 1024 * 1024
ALLOWED_IMAGE = {".jpg", ".jpeg", ".png", ".webp"}
TEACHER_ROLES = ("teacher",)
REVIEW_ROLES = ("teacher", "administrator")
SETTINGS_ROLES = ("administrator",)
VIEW_ROLES = ("teacher", "student", "administrator")


def _now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    if value is None:
        return _now().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _jsonish(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    return default if default is not None else {}


def _hash(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _public_id():
    return "att_" + secrets.token_urlsafe(16)


def _token():
    return secrets.token_urlsafe(32)


def _code():
    return f"{secrets.randbelow(1_000_000):06d}"


def actor_name(session):
    if not session:
        return ""
    if session.get("teacher_data"):
        return session["teacher_data"].get("username") or session["teacher_data"].get("name") or ""
    if session.get("staff_data"):
        return session["staff_data"].get("username") or session["staff_data"].get("name") or ""
    if session.get("student_data"):
        return session["student_data"].get("name") or ""
    return session.get("user_role") or ""


def actor_id(session):
    role = (session or {}).get("user_role")
    if role == "student":
        return str((session.get("student_data") or {}).get("student_id") or "")
    if role == "teacher":
        return str((session.get("teacher_data") or {}).get("teacher_id") or "")
    return str((session.get("staff_data") or {}).get("staff_id") or actor_name(session))


def audit(session, action, attendance_session_id="", student_id="", previous="", new="", reason=""):
    store.insert("attendance_audit", {
        "institution_id": P.INSTITUTION_ID,
        "actor": actor_name(session),
        "actor_role": (session or {}).get("user_role") or "",
        "action": action,
        "attendance_session_id": attendance_session_id,
        "student_id": student_id if student_id != "" else None,
        "previous_state": previous,
        "new_state": new,
        "reason": (reason or "")[:400],
        "created_at": _iso(),
    })


def _rate(session, action):
    key = f"{(session or {}).get('user_role')}:{actor_id(session)}:{action}"
    now = time.time()
    bucket = _RATES[key]
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMITS.get(action, 20):
        return False
    bucket.append(now)
    return True


def get_settings():
    rows = store.select("secure_attendance_settings") or []
    raw = _jsonish(rows[0].get("settings"), {}) if rows else {}
    return P.normalize_settings(raw)


def save_settings(raw, session):
    cfg = P.normalize_settings({**get_settings(), **(raw or {})})
    existing = store.select("secure_attendance_settings") or []
    payload = {"settings": cfg, "updated_at": _iso()}
    if existing:
        store.update("secure_attendance_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        store.insert("secure_attendance_settings", {"id": 1, **payload})
    audit(session, "attendance_settings_updated")
    return cfg


def _teacher_id(session):
    return _int((session.get("teacher_data") or {}).get("teacher_id"))


def _student_id(session):
    return _int((session.get("student_data") or {}).get("student_id"))


def _load_subject(session, subject_id):
    teacher_id = _teacher_id(session)
    if teacher_id is None:
        return None, "FORBIDDEN"
    from src.database.config import is_supabase_configured as cloud_on
    if cloud_on():
        from src.database import db as cloud
        subjects = cloud.get_teacher_subjects(teacher_id) or []
    else:
        from src.database import local_store as local
        subjects = local.teacher_subjects(teacher_id)
    for row in subjects:
        if _int(row.get("subject_id")) == _int(subject_id):
            return row, ""
    return None, "SUBJECT_NOT_YOURS"


def _roster(session, subject_id):
    teacher_id = _teacher_id(session)
    if teacher_id is None:
        return []
    if is_supabase_configured():
        from src.database import db as cloud
        from src.database.config import supabase
        subjects = cloud.get_teacher_subjects(teacher_id) or []
        if not any(_int(row.get("subject_id")) == _int(subject_id) for row in subjects):
            return []
        enrollments = supabase.table("subject_students").select("student_id").eq("subject_id", subject_id).execute().data or []
        ids = {_int(row["student_id"]) for row in enrollments}
        return [
            row for row in (cloud.get_all_students("student_id, name") or [])
            if _int(row.get("student_id")) in ids
        ]
    from src.database import local_store as local
    subjects = local.teacher_subjects(teacher_id)
    if not any(_int(row.get("subject_id")) == _int(subject_id) for row in subjects):
        return []
    return local.students_for_subject(subject_id)


def _write_attendance_log(student_id, subject_id, present=True):
    stamp = _iso()
    log = {
        "student_id": int(student_id),
        "subject_id": int(subject_id),
        "is_present": bool(present),
        "timestamp": stamp,
    }
    if is_supabase_configured():
        from src.database import db as cloud
        cloud.create_attendance([log])
    else:
        from src.database import local_store as local
        local.add_attendance([log])
    return stamp


def create_session(session, body):
    cfg = get_settings()
    if not cfg.get("ai_attendance_enabled"):
        return None, "FEATURE_DISABLED"
    if session.get("user_role") not in TEACHER_ROLES:
        return None, "FORBIDDEN"
    if not _rate(session, "create"):
        return None, "RATE_LIMITED"
    subject_id = _int(body.get("subjectId") if body.get("subjectId") is not None else body.get("subject_id"))
    subject, err = _load_subject(session, subject_id)
    if err:
        return None, err
    minutes = _int(body.get("durationMinutes") if body.get("durationMinutes") is not None else body.get("duration_minutes"), cfg["session_duration_minutes"])
    minutes = max(1, min(180, minutes or cfg["session_duration_minutes"]))
    start = _now()
    expires = start + timedelta(minutes=minutes)
    public_id = _public_id()
    row = {
        "institution_id": P.INSTITUTION_ID,
        "public_id": public_id,
        "subject_id": subject_id,
        "subject_code": subject.get("subject_code"),
        "subject_name": subject.get("name"),
        "section": subject.get("section") or "",
        "teacher_id": _teacher_id(session),
        "teacher_name": (session.get("teacher_data") or {}).get("name") or actor_name(session),
        "lecture": str(body.get("lecture") or "")[:80],
        "status": P.SESSION_ACTIVE,
        "verification_mode": cfg["verification_mode"],
        "started_at": _iso(start),
        "expires_at": _iso(expires),
        "created_at": _iso(start),
    }
    saved = store.insert("attendance_sessions", row)
    if not saved:
        return None, "SAVE_FAILED"
    item = saved[0]
    for student in _roster(session, subject_id):
        store.insert("attendance_marks", {
            "institution_id": P.INSTITUTION_ID,
            "session_id": item.get("id"),
            "session_public_id": public_id,
            "student_id": student.get("student_id"),
            "student_name": student.get("name"),
            "status": P.MARK_PENDING_FACE,
            "source": None,
            "created_at": _iso(),
        })
    audit(session, "session_created", public_id)
    return session_out(item), ""


def _session_by_public(public_id):
    rows = [row for row in (store.select("attendance_sessions") or []) if str(row.get("public_id")) == str(public_id)]
    return rows[0] if rows else None


def _marks(session_id):
    return [row for row in (store.select("attendance_marks") or []) if str(row.get("session_id")) == str(session_id) or str(row.get("session_public_id")) == str(session_id)]


def _refresh_session(row):
    if not row:
        return row
    if row.get("status") != P.SESSION_ACTIVE:
        return row
    exp = P.parse_ts(row.get("expires_at"))
    if exp and _now() > exp:
        store.update("attendance_sessions", {"id": row.get("id")}, {"status": P.SESSION_EXPIRED})
        row = {**row, "status": P.SESSION_EXPIRED}
        for mark in _marks(row.get("id")):
            if mark.get("status") in (P.MARK_VERIFICATION_PENDING, P.MARK_FACE_MATCHED, P.MARK_PENDING_FACE):
                store.update("attendance_marks", {"id": mark.get("id")}, {"status": P.MARK_EXPIRED})
    return row


def session_out(row, include_students=True):
    row = _refresh_session(row)
    marks = _marks(row.get("id")) if include_students else []
    counts = {
        "total": len(marks),
        "detected": sum(1 for m in marks if m.get("face_status") in (P.FACE_MATCHED, P.FACE_UNCERTAIN, P.FACE_DETECTED)),
        "matched": sum(1 for m in marks if m.get("face_status") == P.FACE_MATCHED or m.get("status") in (P.MARK_FACE_MATCHED, P.MARK_VERIFICATION_PENDING, P.MARK_VERIFIED, P.MARK_PRESENT)),
        "pending": sum(1 for m in marks if m.get("status") == P.MARK_VERIFICATION_PENDING),
        "verified": sum(1 for m in marks if m.get("status") in (P.MARK_VERIFIED, P.MARK_PRESENT)),
        "present": sum(1 for m in marks if m.get("status") == P.MARK_PRESENT),
        "review": sum(1 for m in marks if m.get("status") == P.MARK_MANUAL_REVIEW),
        "unknown": sum(1 for m in (store.select("attendance_face_results") or []) if str(row.get("id")) == str(m.get("session_id")) and m.get("recognition_status") in (P.FACE_UNKNOWN, P.FACE_UNCERTAIN) and not m.get("student_id")),
        "rejected": sum(1 for m in marks if m.get("status") == P.MARK_REJECTED),
    }
    unknown_faces = [m for m in (store.select("attendance_face_results") or []) if str(m.get("session_id")) == str(row.get("id")) and m.get("recognition_status") in (P.FACE_UNKNOWN, P.FACE_UNCERTAIN) and not m.get("student_id")]
    counts["unknown"] = len(unknown_faces)
    students = []
    if include_students:
        for mark in marks:
            students.append({
                "studentId": mark.get("student_id"),
                "name": mark.get("student_name"),
                "status": mark.get("status"),
                "faceStatus": mark.get("face_status"),
                "confidence": mark.get("confidence"),
                "verificationMethod": mark.get("verification_method"),
                "verifiedAt": mark.get("verified_at"),
                "source": mark.get("source"),
            })
    return {
        "id": row.get("public_id"),
        "subjectId": row.get("subject_id"),
        "subjectCode": row.get("subject_code"),
        "subjectName": row.get("subject_name"),
        "section": row.get("section"),
        "lecture": row.get("lecture"),
        "facultyName": row.get("teacher_name"),
        "status": row.get("status"),
        "verificationMode": row.get("verification_mode"),
        "startedAt": row.get("started_at"),
        "expiresAt": row.get("expires_at"),
        "counts": counts,
        "students": students,
    }


def list_teacher_sessions(session):
    if session.get("user_role") not in REVIEW_ROLES:
        return [], "FORBIDDEN"
    teacher_id = _teacher_id(session)
    rows = store.select("attendance_sessions") or []
    if session.get("user_role") == "teacher":
        rows = [row for row in rows if _int(row.get("teacher_id")) == teacher_id]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return [session_out(row, include_students=False) for row in rows[:40]], ""


def get_session(session, public_id):
    row = _session_by_public(public_id)
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") == "teacher" and _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    if session.get("user_role") == "student":
        return None, "FORBIDDEN"
    return session_out(row), ""


def _confidence(distance, threshold):
    if distance is None:
        return None
    try:
        dist = float(distance)
    except (TypeError, ValueError):
        return None
    # L2 distance: 0 is perfect. Map through the project threshold.
    score = max(0.0, min(1.0, 1.0 - (dist / max(0.01, float(threshold) * 1.6))))
    return round(score, 3)


def score_classroom(image_np, roster_ids, threshold=None, uncertain_mult=1.2):
    """Reuse the existing dlib pipeline. Never force the closest student."""
    from src.pipelines.face_pipeline import MATCH_THRESHOLD, get_face_embeddings, get_trained_model, nearest_face_match

    cutoff = float(threshold if threshold is not None else MATCH_THRESHOLD)
    encodings = get_face_embeddings(image_np)
    model = get_trained_model()
    if not model or model == 0:
        return [], len(encodings), "AI analysis temporarily unavailable."
    X_train = model.get("X") or []
    y_train = model.get("y") or []
    if not X_train:
        return [], len(encodings), "AI analysis temporarily unavailable."
    used = set()
    results = []
    for encoding in encodings:
        sid, dist = nearest_face_match(encoding, X_train, y_train)
        conf = _confidence(dist, cutoff)
        if sid is None or (roster_ids and int(sid) not in roster_ids):
            results.append({"studentId": None, "distance": dist, "confidence": conf, "status": P.FACE_UNKNOWN})
            continue
        if int(sid) in used:
            results.append({"studentId": None, "distance": dist, "confidence": conf, "status": P.FACE_UNKNOWN})
            continue
        if dist <= cutoff:
            used.add(int(sid))
            results.append({"studentId": int(sid), "distance": dist, "confidence": conf, "status": P.FACE_MATCHED})
        elif dist <= cutoff * float(uncertain_mult):
            results.append({"studentId": None, "distance": dist, "confidence": conf, "status": P.FACE_UNCERTAIN})
        else:
            results.append({"studentId": None, "distance": dist, "confidence": conf, "status": P.FACE_UNKNOWN})
    return results, len(encodings), ""


def _validate_image(filename, data):
    if not data:
        return None, "INVALID_IMAGE"
    if len(data) > MAX_IMAGE_BYTES:
        return None, "INVALID_IMAGE"
    name = str(filename or "capture.jpg").lower()
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    if ext not in ALLOWED_IMAGE:
        return None, "INVALID_IMAGE"
    try:
        from PIL import Image
        import numpy as np
        parsed = Image.open(io.BytesIO(data)).convert("RGB")
        if min(parsed.size) < 8:
            return None, "INVALID_IMAGE"
        return np.array(parsed), ""
    except Exception:
        return None, "INVALID_IMAGE"


def analyze_session(session, public_id, uploads):
    cfg = get_settings()
    if not cfg.get("ai_attendance_enabled"):
        return None, "FEATURE_DISABLED"
    if session.get("user_role") not in TEACHER_ROLES:
        return None, "FORBIDDEN"
    if not _rate(session, "analyze"):
        return None, "RATE_LIMITED"
    row = _refresh_session(_session_by_public(public_id))
    if not row:
        return None, "NOT_FOUND"
    if _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    if row.get("status") != P.SESSION_ACTIVE:
        return None, "SESSION_INACTIVE"
    if not uploads:
        return None, "IMAGE_REQUIRED"
    roster = _roster(session, row.get("subject_id"))
    roster_ids = {_int(item.get("student_id")) for item in roster}
    names = {_int(item.get("student_id")): item.get("name") for item in roster}
    scored = []
    error = ""
    for upload in uploads:
        filename = upload.get("filename") if isinstance(upload, dict) else getattr(upload, "filename", "capture.jpg")
        data = upload.get("bytes") if isinstance(upload, dict) else upload
        image_np, err = _validate_image(filename, data)
        if err:
            return None, err
        try:
            faces, _count, msg = score_classroom(image_np, roster_ids, uncertain_mult=cfg.get("uncertain_multiplier") or 1.2)
        except Exception:
            logger.exception("face analysis failed")
            return None, "AI_UNAVAILABLE"
        if msg:
            error = msg
        scored.extend(faces)
    if error and not scored:
        return None, "AI_UNAVAILABLE"
    ingest_face_results(session, row, scored, names)
    audit(session, "session_analyzed", row.get("public_id"), reason=f"{len(scored)} faces")
    return session_out(row), ""


def ingest_face_results(session, row, scored, names=None):
    names = names or {}
    issued = 0
    for face in scored or []:
        store.insert("attendance_face_results", {
            "institution_id": P.INSTITUTION_ID,
            "session_id": row.get("id"),
            "session_public_id": row.get("public_id"),
            "student_id": face.get("studentId"),
            "confidence": face.get("confidence"),
            "distance": face.get("distance"),
            "recognition_status": face.get("status"),
            "created_at": _iso(),
        })
        sid = _int(face.get("studentId"))
        if face.get("status") != P.FACE_MATCHED or sid is None:
            continue
        mark = _mark_for(row, sid)
        if not mark:
            continue
        if mark.get("status") == P.MARK_PRESENT:
            continue
        store.update("attendance_marks", {"id": mark.get("id")}, {
            "status": P.MARK_VERIFICATION_PENDING,
            "face_status": P.FACE_MATCHED,
            "confidence": face.get("confidence"),
        })
        _issue_challenges(row, sid, names.get(sid) or mark.get("student_name"))
        issued += 1
    return issued


def _mark_for(row, student_id):
    for mark in _marks(row.get("id")):
        if _int(mark.get("student_id")) == _int(student_id):
            return mark
    return None


def _issue_challenges(row, student_id, student_name=""):
    cfg = get_settings()
    mode = row.get("verification_mode") or cfg["verification_mode"]
    if mode == P.MODE_FACE_ONLY:
        return
    existing = [
        tok for tok in (store.select("attendance_tokens") or [])
        if str(tok.get("session_id")) == str(row.get("id")) and _int(tok.get("student_id")) == _int(student_id) and tok.get("status") == "ISSUED"
    ]
    if existing:
        notifier.notify(
            role="student",
            recipient_id=student_id,
            title=f"Attendance verification required for {row.get('subject_code') or row.get('subject_name')}",
            body="Open Verify Attendance to confirm you are present. Face match alone is not attendance.",
        )
        return
    if P.requires_student_token(mode) or mode == P.MODE_FACE_PLUS_INAPP:
        raw = _token()
        store.insert("attendance_tokens", {
            "institution_id": P.INSTITUTION_ID,
            "session_id": row.get("id"),
            "session_public_id": row.get("public_id"),
            "student_id": student_id,
            "kind": P.METHOD_QR,
            "token_hash": _hash(raw),
            "token_hint": raw[:4],
            "status": "ISSUED",
            "expires_at": _iso(_now() + timedelta(seconds=cfg["qr_expiry_seconds"])),
            "created_at": _iso(),
        })
    # Secret codes are issued only when the authenticated student requests one.
    notifier.notify(
        role="student",
        recipient_id=student_id,
        title=f"Attendance verification required for {row.get('subject_code') or row.get('subject_name')}",
        body=f"{row.get('subject_name') or 'Class'} with {row.get('teacher_name') or 'faculty'}. Verify before the session expires.",
    )
    if cfg.get("email_verification_enabled"):
        logger.info("email verification requested but no mail transport is configured")


def _active_hold_code(row, student_id):
    holds = [
        tok for tok in (store.select("attendance_tokens") or [])
        if str(tok.get("session_id")) == str(row.get("id"))
        and _int(tok.get("student_id")) == _int(student_id)
        and tok.get("kind") == "CODE_PLAIN_HOLD"
        and tok.get("status") == "HOLD"
    ]
    if not holds:
        return None
    hold = holds[-1]
    exp = P.parse_ts(hold.get("expires_at"))
    if exp and _now() > exp:
        return None
    return hold.get("hold_code")


def student_pending(session):
    sid = _student_id(session)
    if sid is None:
        return [], "FORBIDDEN"
    out = []
    for row in store.select("attendance_sessions") or []:
        row = _refresh_session(row)
        mark = _mark_for(row, sid)
        if not mark:
            continue
        if mark.get("status") not in (P.MARK_VERIFICATION_PENDING, P.MARK_FACE_MATCHED, P.MARK_MANUAL_REVIEW):
            continue
        if row.get("status") != P.SESSION_ACTIVE:
            continue
        out.append({
            "id": row.get("public_id"),
            "subjectCode": row.get("subject_code"),
            "subjectName": row.get("subject_name"),
            "facultyName": row.get("teacher_name"),
            "lecture": row.get("lecture"),
            "startedAt": row.get("started_at"),
            "expiresAt": row.get("expires_at"),
            "status": mark.get("status"),
            "verificationRequired": True,
            "mode": row.get("verification_mode"),
        })
    return out, ""


def student_history(session):
    sid = _student_id(session)
    if sid is None:
        return [], "FORBIDDEN"
    rows = [mark for mark in (store.select("attendance_marks") or []) if _int(mark.get("student_id")) == sid]
    rows.sort(key=lambda row: str(row.get("verified_at") or row.get("created_at") or ""), reverse=True)
    out = []
    sessions = {row.get("id"): row for row in (store.select("attendance_sessions") or [])}
    public = {row.get("public_id"): row for row in sessions.values()}
    for mark in rows[:80]:
        sess = sessions.get(mark.get("session_id")) or public.get(mark.get("session_public_id"))
        out.append({
            "subjectCode": (sess or {}).get("subject_code"),
            "subjectName": (sess or {}).get("subject_name"),
            "facultyName": (sess or {}).get("teacher_name"),
            "status": mark.get("status"),
            "verificationMethod": mark.get("verification_method"),
            "source": mark.get("source"),
            "verifiedAt": mark.get("verified_at"),
            "startedAt": (sess or {}).get("started_at"),
        })
    return out, ""


def issue_qr(session, public_id):
    cfg = get_settings()
    if not cfg.get("qr_verification_enabled"):
        return None, "FEATURE_DISABLED"
    if not _rate(session, "qr"):
        return None, "RATE_LIMITED"
    sid = _student_id(session)
    row = _refresh_session(_session_by_public(public_id))
    err = _student_guard(session, row, sid)
    if err:
        return None, err
    for tok in store.select("attendance_tokens") or []:
        if str(tok.get("session_id")) == str(row.get("id")) and _int(tok.get("student_id")) == sid and tok.get("kind") == P.METHOD_QR and tok.get("status") == "ISSUED":
            store.update("attendance_tokens", {"id": tok.get("id")}, {"status": "ROTATED"})
    raw = _token()
    store.insert("attendance_tokens", {
        "institution_id": P.INSTITUTION_ID,
        "session_id": row.get("id"),
        "session_public_id": row.get("public_id"),
        "student_id": sid,
        "kind": P.METHOD_QR,
        "token_hash": _hash(raw),
        "token_hint": raw[:4],
        "status": "ISSUED",
        "expires_at": _iso(_now() + timedelta(seconds=cfg["qr_expiry_seconds"])),
        "created_at": _iso(),
    })
    audit(session, "qr_issued", row.get("public_id"), sid)
    return {
        "token": raw,
        "expiresInSeconds": cfg["qr_expiry_seconds"],
        "hint": "This code is short-lived and single-use. Do not share it.",
    }, ""


def issue_code(session, public_id):
    cfg = get_settings()
    if not cfg.get("secret_code_enabled"):
        return None, "FEATURE_DISABLED"
    if not _rate(session, "code"):
        return None, "RATE_LIMITED"
    sid = _student_id(session)
    row = _refresh_session(_session_by_public(public_id))
    err = _student_guard(session, row, sid)
    if err:
        return None, err
    for tok in store.select("attendance_tokens") or []:
        if str(tok.get("session_id")) == str(row.get("id")) and _int(tok.get("student_id")) == sid and tok.get("kind") in (P.METHOD_CODE, "CODE_PLAIN_HOLD") and tok.get("status") in ("ISSUED", "HOLD"):
            store.update("attendance_tokens", {"id": tok.get("id")}, {"status": "ROTATED"})
    code = _code()
    store.insert("attendance_tokens", {
        "institution_id": P.INSTITUTION_ID,
        "session_id": row.get("id"),
        "session_public_id": row.get("public_id"),
        "student_id": sid,
        "kind": P.METHOD_CODE,
        "token_hash": _hash(f"{row.get('public_id')}:{sid}:{code}"),
        "status": "ISSUED",
        "expires_at": _iso(_now() + timedelta(seconds=cfg["code_expiry_seconds"])),
        "created_at": _iso(),
    })
    audit(session, "code_issued", row.get("public_id"), sid)
    return {"code": code, "expiresInSeconds": cfg["code_expiry_seconds"]}, ""


def register_device(session, existing_secret=""):
    sid = _student_id(session)
    if sid is None:
        return None, "FORBIDDEN"
    if existing_secret:
        found = [
            row for row in (store.select("attendance_devices") or [])
            if _int(row.get("student_id")) == sid and row.get("secret_hash") == _hash(existing_secret) and row.get("status") == "ACTIVE"
        ]
        if found:
            store.update("attendance_devices", {"id": found[0].get("id")}, {"last_used_at": _iso()})
            return {"deviceToken": existing_secret, "registered": True}, ""
    secret = _token()
    store.insert("attendance_devices", {
        "institution_id": P.INSTITUTION_ID,
        "student_id": sid,
        "secret_hash": _hash(secret),
        "status": "ACTIVE",
        "registered_at": _iso(),
        "last_used_at": _iso(),
    })
    audit(session, "device_registered", student_id=sid)
    return {"deviceToken": secret, "registered": True}, ""


def _student_guard(session, row, student_id):
    if session.get("user_role") != "student":
        return "FORBIDDEN"
    if student_id is None:
        return "FORBIDDEN"
    if not row:
        return "NOT_FOUND"
    if row.get("status") != P.SESSION_ACTIVE:
        return "SESSION_INACTIVE"
    mark = _mark_for(row, student_id)
    if not mark:
        return "NOT_ENROLLED"
    if mark.get("status") == P.MARK_PRESENT:
        return "ALREADY_PRESENT"
    if mark.get("status") not in (P.MARK_VERIFICATION_PENDING, P.MARK_FACE_MATCHED, P.MARK_MANUAL_REVIEW):
        return "NOT_ELIGIBLE"
    return ""


def _find_token(kind, token_hash=None, session_id=None, student_id=None):
    for tok in store.select("attendance_tokens") or []:
        if kind and tok.get("kind") != kind:
            continue
        if token_hash and tok.get("token_hash") != token_hash:
            continue
        if session_id is not None and str(tok.get("session_id")) != str(session_id):
            continue
        if student_id is not None and _int(tok.get("student_id")) != _int(student_id):
            continue
        return tok
    return None


def confirm_verification(session, body):
    cfg = get_settings()
    if not cfg.get("ai_attendance_enabled"):
        return None, "FEATURE_DISABLED"
    if not _rate(session, "verify"):
        return None, "RATE_LIMITED"
    sid = _student_id(session)
    public_id = body.get("sessionId") or body.get("session_id")
    row = _refresh_session(_session_by_public(public_id))
    err = _student_guard(session, row, sid)
    if err:
        return None, err
    mode = row.get("verification_mode") or cfg["verification_mode"]
    mark = _mark_for(row, sid)
    if mark.get("face_status") != P.FACE_MATCHED:
        return None, "FACE_NOT_MATCHED"

    with _TX:
        mark = _mark_for(row, sid)
        if mark.get("status") == P.MARK_PRESENT:
            return None, "ALREADY_PRESENT"
        method = None
        if P.requires_student_token(mode):
            raw = str(body.get("token") or "").strip()
            if not raw:
                return None, "TOKEN_REQUIRED"
            tok = _find_token(P.METHOD_QR, token_hash=_hash(raw))
            if not tok:
                return None, "TOKEN_INVALID"
            if _int(tok.get("student_id")) != sid or str(tok.get("session_id")) != str(row.get("id")):
                return None, "TOKEN_MISMATCH"
            if tok.get("status") != "ISSUED":
                return None, "TOKEN_USED"
            exp = P.parse_ts(tok.get("expires_at"))
            if exp and _now() > exp:
                store.update("attendance_tokens", {"id": tok.get("id")}, {"status": "EXPIRED"})
                return None, "TOKEN_EXPIRED"
            store.update("attendance_tokens", {"id": tok.get("id"), "status": "ISSUED"}, {"status": "USED", "used_at": _iso()})
            method = P.METHOD_QR
        elif P.requires_secret_code(mode):
            if not _rate(session, "code"):
                return None, "RATE_LIMITED"
            code = str(body.get("code") or "").strip()
            if not code:
                return None, "CODE_REQUIRED"
            digest = _hash(f"{row.get('public_id')}:{sid}:{code}")
            tok = _find_token(P.METHOD_CODE, token_hash=digest, session_id=row.get("id"), student_id=sid)
            if not tok or tok.get("status") != "ISSUED":
                return None, "CODE_INVALID"
            exp = P.parse_ts(tok.get("expires_at"))
            if exp and _now() > exp:
                store.update("attendance_tokens", {"id": tok.get("id")}, {"status": "EXPIRED"})
                return None, "TOKEN_EXPIRED"
            store.update("attendance_tokens", {"id": tok.get("id"), "status": "ISSUED"}, {"status": "USED", "used_at": _iso()})
            method = P.METHOD_CODE
        elif mode == P.MODE_FACE_PLUS_INAPP:
            method = P.METHOD_INAPP
        else:
            return None, "VERIFICATION_REQUIRED"

        if P.requires_device(mode, cfg.get("device_binding_enabled")):
            secret = str(body.get("deviceToken") or body.get("device_token") or "").strip()
            devices = [d for d in (store.select("attendance_devices") or []) if _int(d.get("student_id")) == sid and d.get("status") == "ACTIVE"]
            if not devices:
                if not secret:
                    issued = register_device(session)[0]
                    secret = (issued or {}).get("deviceToken")
                    body["deviceToken"] = secret
                else:
                    register_device(session, secret)
            else:
                if not secret or not any(hmac.compare_digest(str(d.get("secret_hash")), _hash(secret)) for d in devices):
                    return None, "DEVICE_MISMATCH"
                store.update("attendance_devices", {"id": devices[0].get("id")}, {"last_used_at": _iso()})

        return _finalize_present(session, row, mark, method, P.SOURCE_VERIFIED)


def _finalize_present(session, row, mark, method, source, reason=""):
    if mark.get("status") == P.MARK_PRESENT:
        return None, "ALREADY_PRESENT"
    previous = mark.get("status")
    stamp = _write_attendance_log(mark.get("student_id"), row.get("subject_id"), present=True)
    store.update("attendance_marks", {"id": mark.get("id")}, {
        "status": P.MARK_PRESENT,
        "verification_method": method,
        "source": source,
        "verified_at": stamp,
        "verified_by": actor_name(session),
    })
    audit(session, "attendance_present", row.get("public_id"), mark.get("student_id"), previous, P.MARK_PRESENT, reason or method)
    notifier.notify(
        role="student",
        recipient_id=mark.get("student_id"),
        title="Attendance verified",
        body=f"{row.get('subject_name') or row.get('subject_code')} is marked present.",
    )
    return {
        "ok": True,
        "status": P.MARK_PRESENT,
        "verifiedAt": stamp,
        "verification": method,
        "subjectName": row.get("subject_name"),
        "sessionValid": True,
    }, ""


def faculty_finalize_matched(session, public_id, reason):
    cfg = get_settings()
    row = _refresh_session(_session_by_public(public_id))
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") not in TEACHER_ROLES or _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    mode = row.get("verification_mode") or cfg["verification_mode"]
    if not P.allows_faculty_finalize(mode):
        return None, "POLICY_FORBIDS_FACE_ONLY"
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    finalized = 0
    for mark in _marks(row.get("id")):
        if mark.get("face_status") == P.FACE_MATCHED and mark.get("status") != P.MARK_PRESENT:
            _finalize_present(session, row, mark, P.METHOD_FACULTY, P.SOURCE_MANUAL, reason)
            finalized += 1
    return {"ok": True, "finalized": finalized}, ""


def correct_mark(session, public_id, student_id, decision, reason):
    if session.get("user_role") not in REVIEW_ROLES:
        return None, "FORBIDDEN"
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    row = _refresh_session(_session_by_public(public_id))
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") == "teacher" and _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    mark = _mark_for(row, student_id)
    if not mark:
        return None, "NOT_FOUND"
    wanted = str(decision or "").upper()
    previous = mark.get("status")
    if wanted in ("PRESENT", "MARK_PRESENT"):
        if previous == P.MARK_PRESENT:
            return session_out(row), ""
        _finalize_present(session, row, mark, P.METHOD_FACULTY, P.SOURCE_MANUAL, reason)
    elif wanted in ("ABSENT", "MARK_ABSENT"):
        store.update("attendance_marks", {"id": mark.get("id")}, {
            "status": P.MARK_ABSENT,
            "source": P.SOURCE_MANUAL,
            "verified_at": _iso(),
            "verified_by": actor_name(session),
            "review_reason": str(reason)[:400],
        })
        _write_attendance_log(student_id, row.get("subject_id"), present=False)
        audit(session, "attendance_absent", row.get("public_id"), student_id, previous, P.MARK_ABSENT, reason)
    elif wanted in ("REJECT", "REJECTED"):
        store.update("attendance_marks", {"id": mark.get("id")}, {
            "status": P.MARK_REJECTED,
            "review_reason": str(reason)[:400],
            "verified_by": actor_name(session),
        })
        audit(session, "attendance_rejected", row.get("public_id"), student_id, previous, P.MARK_REJECTED, reason)
    elif wanted in ("REVIEW", "MANUAL_REVIEW"):
        store.update("attendance_marks", {"id": mark.get("id")}, {"status": P.MARK_MANUAL_REVIEW, "review_reason": str(reason)[:400]})
        audit(session, "attendance_review", row.get("public_id"), student_id, previous, P.MARK_MANUAL_REVIEW, reason)
    else:
        return None, "UNKNOWN_DECISION"
    return session_out(row), ""


def complete_session(session, public_id, reason=""):
    row = _refresh_session(_session_by_public(public_id))
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") not in TEACHER_ROLES or _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    store.update("attendance_sessions", {"id": row.get("id")}, {"status": P.SESSION_COMPLETED, "completed_at": _iso()})
    for mark in _marks(row.get("id")):
        if mark.get("status") in (P.MARK_VERIFICATION_PENDING, P.MARK_PENDING_FACE, P.MARK_FACE_MATCHED):
            store.update("attendance_marks", {"id": mark.get("id")}, {"status": P.MARK_EXPIRED})
    audit(session, "session_completed", public_id, reason=reason)
    return session_out({**row, "status": P.SESSION_COMPLETED}), ""


def cancel_session(session, public_id, reason):
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    row = _session_by_public(public_id)
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") not in REVIEW_ROLES:
        return None, "FORBIDDEN"
    if session.get("user_role") == "teacher" and _int(row.get("teacher_id")) != _teacher_id(session):
        return None, "FORBIDDEN"
    store.update("attendance_sessions", {"id": row.get("id")}, {"status": P.SESSION_CANCELLED, "cancel_reason": str(reason)[:400]})
    audit(session, "session_cancelled", public_id, reason=reason)
    return session_out({**row, "status": P.SESSION_CANCELLED}), ""


def create_dispute(session, public_id, reason):
    sid = _student_id(session)
    if sid is None:
        return None, "FORBIDDEN"
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    row = _session_by_public(public_id)
    if not row:
        return None, "NOT_FOUND"
    mark = _mark_for(row, sid)
    if not mark:
        return None, "NOT_ENROLLED"
    saved = store.insert("attendance_disputes", {
        "institution_id": P.INSTITUTION_ID,
        "session_id": row.get("id"),
        "session_public_id": row.get("public_id"),
        "student_id": sid,
        "reason": str(reason)[:400],
        "status": "OPEN",
        "created_at": _iso(),
    })
    audit(session, "attendance_dispute", public_id, sid, reason=reason)
    notifier.notify(role="teacher", recipient_id=row.get("teacher_id"), title="Attendance dispute", body="A student opened an attendance dispute.")
    return {"ok": True, "id": (saved or [{}])[0].get("id")}, ""


def email_status():
    cfg = get_settings()
    if not cfg.get("email_verification_enabled"):
        return {"configured": False, "enabled": False, "message": "College email verification is turned off."}
    return {
        "configured": False,
        "enabled": True,
        "message": "Verification delivery failed. No college email service is configured. Use in-app QR or secret code.",
    }


def analytics(session):
    if session.get("user_role") not in REVIEW_ROLES:
        return None, "FORBIDDEN"
    marks = store.select("attendance_marks") or []
    if session.get("user_role") == "teacher":
        owned = {row.get("id") for row in (store.select("attendance_sessions") or []) if _int(row.get("teacher_id")) == _teacher_id(session)}
        marks = [row for row in marks if row.get("session_id") in owned]
    present = [row for row in marks if row.get("status") == P.MARK_PRESENT]
    verified = [row for row in present if row.get("source") == P.SOURCE_VERIFIED]
    manual = [row for row in present if row.get("source") == P.SOURCE_MANUAL]
    return {
        "marks": len(marks),
        "present": len(present),
        "verifiedAi": len(verified),
        "manual": len(manual),
        "pending": sum(1 for row in marks if row.get("status") == P.MARK_VERIFICATION_PENDING),
        "rejected": sum(1 for row in marks if row.get("status") == P.MARK_REJECTED),
        "expired": sum(1 for row in marks if row.get("status") == P.MARK_EXPIRED),
        "note": "PENDING, REJECTED, and EXPIRED are not counted as present.",
    }, ""
