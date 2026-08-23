"""Misconduct complaints. Faculty request moderation; only an administrator executes it.

Anonymous mentorship aliases (STU-…) are resolved server-side. Faculty payloads
never include student name, enrollment, email, or phone because a complaint was filed.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone

from src.database.config import is_supabase_configured, supabase
from src.database.db import get_student_public, get_teacher_public
from src.moderation import policy as P
from src.success import store
from src.success.staff_auth import get_staff_public

REVEALED = ("ACCEPTED", "IDENTITIES_REVEALED")


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
    return store.available("complaints") and store.available("student_moderation_status")


def _demo(session_state) -> bool:
    return bool(session_state and session_state.get("demo_mode"))


def _code() -> str:
    return f"CMP-{uuid.uuid4().hex[:8].upper()}"


def public_complaint_id(row) -> str:
    if not row:
        return ""
    code = str(row.get("complaint_code") or row.get("complaintCode") or "").strip()
    if code:
        return code.upper() if code.upper().startswith("CMP-") else code
    cid = row.get("complaint_id") or row.get("complaintId")
    if cid:
        return f"CMP-{str(cid).replace('-', '')[:8].upper()}"
    return ""


def _notify_event(*, role, recipient_id, title, body):
    if not title or recipient_id in (None, ""):
        return
    try:
        from src.success.notify import notify
        notify(role=role, recipient_id=recipient_id, title=title, body=body)
    except Exception:
        pass


def _notify_reporter(row, title, body, reporter_role=None, reporter_staff_id=None, reporter_teacher_id=None):
    staff_id = reporter_staff_id if reporter_staff_id is not None else (row or {}).get("reporter_staff_id")
    teacher_id = reporter_teacher_id if reporter_teacher_id is not None else (row or {}).get("reporter_teacher_id")
    role = reporter_role
    if staff_id is not None:
        if not role:
            staff = get_staff_public(staff_id) or {}
            role = staff.get("role") or "faculty"
        _notify_event(role=role, recipient_id=staff_id, title=title, body=body)
        return
    if teacher_id is not None:
        _notify_event(role="teacher", recipient_id=teacher_id, title=title, body=body)


def _audit(*, actor_role, actor_ref, action, complaint_id=None, student_id=None,
           previous_status=None, new_status=None, reason=None, metadata=None):
    store.insert("moderation_audit_logs", {
        "actor_role": actor_role,
        "actor_ref": str(actor_ref or ""),
        "action": action,
        "complaint_id": complaint_id,
        "student_id": student_id,
        "previous_status": previous_status,
        "new_status": new_status,
        "reason": (reason or "")[:2000],
        "metadata": json.dumps(metadata) if isinstance(metadata, dict) else (metadata or None),
    })


def effective_status(student_id):
    """Return (status, until_at, reason). Expired restrictions become ACTIVE."""
    if not installed() or student_id is None:
        return "ACTIVE", None, None
    try:
        student_id = int(student_id)
    except (TypeError, ValueError):
        return "ACTIVE", None, None
    rows = store.select("student_moderation_status", student_id=student_id) or []
    if not rows:
        return "ACTIVE", None, None
    row = rows[0]
    status = row.get("status") or "ACTIVE"
    until = _parse(row.get("until_at"))
    if status in ("RESTRICTED", "SUSPENDED") and until and until <= _now():
        store.update("student_moderation_status", {"student_id": student_id}, {
            "status": "ACTIVE",
            "until_at": None,
            "reason": "Restriction expired",
            "updated_at": _now().isoformat(),
        })
        _audit(
            actor_role="system", actor_ref="expiry", action="BAN_REVOKED",
            student_id=student_id, previous_status=status, new_status="ACTIVE",
            reason="Timed restriction elapsed",
        )
        return "ACTIVE", None, None
    return status, row.get("until_at"), row.get("reason")


def login_allowed(student_id):
    status, _, _ = effective_status(student_id)
    if P.login_allowed_for(status):
        return True, ""
    return False, P.login_message(status)


def participation_allowed(student_id):
    status, _, _ = effective_status(student_id)
    return P.can_participate(status)


def student_snapshot(student_id):
    status, until, reason = effective_status(student_id)
    return {
        "studentId": student_id,
        "status": status,
        "untilAt": until,
        "reason": reason if status != "ACTIVE" else None,
        "canLogin": P.login_allowed_for(status),
        "canParticipate": P.can_participate(status),
        "canAppeal": P.can_appeal(status),
        "banner": P.account_banner(status, until),
    }


def _set_status(student_id, status, *, admin_staff_id, reason, until_at=None, complaint_id=None, action_name=None):
    prev, _, _ = effective_status(student_id)
    payload = {
        "student_id": int(student_id),
        "status": status,
        "until_at": until_at,
        "reason": (reason or "")[:2000],
        "updated_by_staff_id": admin_staff_id,
        "updated_at": _now().isoformat(),
    }
    existing = store.select("student_moderation_status", student_id=int(student_id)) or []
    if existing:
        store.update("student_moderation_status", {"student_id": int(student_id)}, payload)
    else:
        store.insert("student_moderation_status", payload)
    _audit(
        actor_role="administrator", actor_ref=admin_staff_id,
        action=action_name or "ACCOUNT_RESTRICTED",
        complaint_id=complaint_id, student_id=int(student_id),
        previous_status=prev, new_status=status, reason=reason,
    )
    return prev, status


def _mentorship_by_alias(alias: str):
    if not alias or not is_supabase_configured():
        return None
    try:
        rows = supabase.table("mentorships").select(
            "mentorship_id,student_id,mentor_staff_id,student_alias,status"
        ).eq("student_alias", alias.strip()).order("created_at", desc=True).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _mentorship_pair(staff_id, student_id):
    if not is_supabase_configured():
        return None
    try:
        rows = supabase.table("mentorships").select(
            "mentorship_id,student_id,mentor_staff_id,student_alias,status"
        ).eq("mentor_staff_id", int(staff_id)).eq("student_id", int(student_id)).order(
            "created_at", desc=True
        ).limit(5).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def _teacher_teaches(teacher_id, student_id) -> bool:
    if not is_supabase_configured() or teacher_id is None:
        return False
    try:
        subjects = supabase.table("subjects").select("subject_id").eq(
            "teacher_id", int(teacher_id)
        ).execute().data or []
        ids = [s["subject_id"] for s in subjects]
        if not ids:
            return False
        rows = supabase.table("subject_students").select("student_id").eq(
            "student_id", int(student_id)
        ).in_("subject_id", ids).limit(1).execute().data or []
        return bool(rows)
    except Exception:
        return False


def resolve_subject(reference: str, *, reporter_role: str, reporter_staff_id=None, teacher_id=None):
    """Map faculty-visible reference → student_id. Never returns PII to the caller contract."""
    ref = (reference or "").strip()
    if not ref:
        return None, "Enter an anonymous student ID or student ID."

    if ref.upper().startswith("STU"):
        row = _mentorship_by_alias(ref.upper() if ref.upper().startswith("STU-") else ref)
        if not row:
            # Try exact stored alias
            row = _mentorship_by_alias(ref)
        if not row:
            return None, "Unknown anonymous student ID."
        if reporter_staff_id is None or int(row["mentor_staff_id"]) != int(reporter_staff_id):
            return None, "You can only report an anonymous student currently or previously assigned to you."
        return {
            "student_id": int(row["student_id"]),
            "mentorship_id": row["mentorship_id"],
            "alias": row.get("student_alias"),
            "identity_protected": row.get("status") not in REVEALED,
        }, None

    try:
        student_id = int(ref)
    except (TypeError, ValueError):
        return None, "Use an anonymous ID like STU-ANON-82741 or a numeric student ID."

    if student_id < 0:
        return None, "Demo identities cannot be reported into production."
    if get_student_public(student_id) is None:
        return None, "Student not found."

    if reporter_role == "teacher":
        if teacher_id is None or not _teacher_teaches(teacher_id, student_id):
            return None, "You can only report a student enrolled in your subject."
        return {"student_id": student_id, "mentorship_id": None, "alias": None, "identity_protected": False}, None

    if reporter_role == "counsellor":
        pair = _mentorship_pair(reporter_staff_id, student_id) if reporter_staff_id else None
        return {
            "student_id": student_id,
            "mentorship_id": (pair or {}).get("mentorship_id"),
            "alias": (pair or {}).get("student_alias"),
            "identity_protected": False,
        }, None

    if reporter_role in ("faculty", "mentor") and reporter_staff_id is not None:
        pair = _mentorship_pair(reporter_staff_id, student_id)
        if not pair:
            return None, "Use the anonymous student ID from your mentorship. Numeric IDs are only allowed after identities are revealed."
        if pair.get("status") not in REVEALED:
            return None, "Identities are still hidden. Report the anonymous student ID shown on the mentorship card."
        return {
            "student_id": student_id,
            "mentorship_id": pair["mentorship_id"],
            "alias": pair.get("student_alias"),
            "identity_protected": False,
        }, None

    return None, "Not authorized to file a complaint."


def _faculty_row(row: dict) -> dict:
    return P.strip_faculty_payload({
        "complaintId": row["complaint_id"],
        "complaintCode": row["complaint_code"],
        "studentReference": row.get("student_alias_snapshot") or "Student (ID you submitted)",
        "category": row.get("category"),
        "severity": row.get("severity"),
        "requestedAction": row.get("requested_action"),
        "status": P.faculty_status_label(row.get("status")),
        "hasEvidence": bool(row.get("has_evidence")),
        "submittedAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "incidentAt": row.get("incident_at"),
    })


def create_complaint(
    *,
    reporter_role: str,
    reporter_staff_id=None,
    teacher_id=None,
    student_reference: str,
    category: str,
    severity: str,
    description: str,
    requested_action: str,
    incident_at=None,
    mentorship_id=None,
    evidence_note=None,
    evidence_file=None,
    session_state=None,
):
    if _demo(session_state):
        return None, "Demo Mode cannot write complaints into production."
    if not P.can_create_complaint(reporter_role):
        return None, "Only faculty, mentors, counsellors, or teachers can submit a complaint."
    if not installed():
        return None, "Moderation schema is not installed. Run supabase/schema_moderation.sql."
    if reporter_role == "teacher" and teacher_id is None:
        return None, "Teacher session required."
    if reporter_role != "teacher" and reporter_staff_id is None:
        return None, "Staff session required."
    if category not in P.CATEGORIES:
        return None, "Choose a valid complaint category."
    if severity not in P.SEVERITIES:
        return None, "Choose a valid severity."
    if requested_action not in P.REQUESTED_ACTIONS.values():
        return None, "Requested action is invalid."
    text = (description or "").strip()
    if len(text) < 20:
        return None, "Describe the incident in at least 20 characters."

    resolved, err = resolve_subject(
        student_reference,
        reporter_role=reporter_role,
        reporter_staff_id=reporter_staff_id,
        teacher_id=teacher_id,
    )
    if err:
        return None, err

    student_id = resolved["student_id"]
    mid = mentorship_id or resolved.get("mentorship_id")
    if not mid:
        mid = None

    parsed_incident = None
    if incident_at:
        parsed = _parse(str(incident_at).strip().replace(" ", "T"))
        parsed_incident = parsed.isoformat() if parsed else None

    open_rows = []
    try:
        q = supabase.table("complaints").select("complaint_id,created_at").eq(
            "student_id", student_id
        ).in_("status", ["SUBMITTED", "UNDER_REVIEW", "INFO_REQUIRED"])
        if reporter_staff_id is not None:
            q = q.eq("reporter_staff_id", int(reporter_staff_id))
        elif teacher_id is not None:
            q = q.eq("reporter_teacher_id", int(teacher_id))
        open_rows = q.execute().data or []
    except Exception:
        open_rows = []
    if open_rows:
        created = _parse(open_rows[0].get("created_at"))
        if created and _now() - created < timedelta(hours=24):
            return None, "A complaint against this student from you is already under review. Duplicate filings are queued for admin review of reporter conduct, not auto-punished."

    code = _code()
    reporter_ref = reporter_staff_id if reporter_staff_id is not None else teacher_id
    payload = {
        "complaint_code": code,
        "reporter_staff_id": reporter_staff_id,
        "reporter_teacher_id": int(teacher_id) if teacher_id is not None and reporter_role == "teacher" else None,
        "student_id": student_id,
        "mentorship_id": mid,
        "student_alias_snapshot": resolved.get("alias"),
        "category": category,
        "severity": severity,
        "incident_at": parsed_incident,
        "description": text[:8000],
        "requested_action": requested_action,
        "status": "SUBMITTED",
        "has_evidence": bool(evidence_note or evidence_file),
    }
    row = store.insert("complaints", {k: v for k, v in payload.items() if v is not None or k == "has_evidence"})
    if not row:
        return None, "Could not save the complaint."
    complaint = row[0]
    cid = complaint["complaint_id"]

    if evidence_note:
        store.insert("complaint_evidence", {
            "complaint_id": cid,
            "note": evidence_note[:4000],
            "added_by_role": reporter_role,
            "added_by_ref": str(reporter_ref),
        })
    if evidence_file:
        err = add_evidence(cid, reporter_role, reporter_ref, evidence_file, actor_is_admin=False)
        if err:
            return _faculty_row(complaint), f"Complaint saved, but evidence was rejected: {err}"

    _audit(
        actor_role=reporter_role, actor_ref=reporter_ref, action="COMPLAINT_CREATED",
        complaint_id=cid, student_id=student_id, new_status="SUBMITTED",
        reason=requested_action, metadata={"identity_protected": resolved.get("identity_protected")},
    )
    code = public_complaint_id(complaint)
    _notify_reporter(
        complaint, f"Complaint {code} submitted",
        "Administration has your complaint. This Complaint ID stays the same after refresh and status updates.",
        reporter_role=reporter_role, reporter_staff_id=reporter_staff_id, reporter_teacher_id=teacher_id,
    )
    _notify_event(
        role="administrator",
        recipient_id="ops",
        title=f"New complaint {code}",
        body="Open Complaint Management to review the new complaint.",
    )
    return _faculty_row(complaint), None


def add_evidence(complaint_id, actor_role, actor_ref, uploaded, *, actor_is_admin=False):
    filename = getattr(uploaded, "name", None) or "upload"
    mime = getattr(uploaded, "type", None) or ""
    data = uploaded.getvalue() if hasattr(uploaded, "getvalue") else uploaded.read()
    err = P.validate_evidence(filename, mime, len(data or b""))
    if err:
        return err
    digest = hashlib.sha256(data).hexdigest()
    store.insert("complaint_evidence", {
        "complaint_id": complaint_id,
        "filename": filename[:200],
        "mime": mime[:80],
        "byte_size": len(data),
        "sha256": digest,
        "note": "File hash stored. Binary is not served publicly.",
        "added_by_role": actor_role,
        "added_by_ref": str(actor_ref),
    })
    store.update("complaints", {"complaint_id": complaint_id}, {
        "has_evidence": True,
        "updated_at": _now().isoformat(),
    })
    _audit(
        actor_role=actor_role, actor_ref=actor_ref, action="EVIDENCE_ADDED",
        complaint_id=complaint_id,
        metadata={"sha256": digest, "filename": filename, "admin": actor_is_admin},
    )
    return None


def list_faculty_complaints(reporter_staff_id=None, teacher_id=None):
    if not installed() or (reporter_staff_id is None and teacher_id is None):
        return []
    try:
        q = supabase.table("complaints").select(
            "complaint_id,complaint_code,student_alias_snapshot,category,severity,"
            "requested_action,status,has_evidence,created_at,updated_at,incident_at"
        )
        if reporter_staff_id is not None:
            q = q.eq("reporter_staff_id", int(reporter_staff_id))
        else:
            q = q.eq("reporter_teacher_id", int(teacher_id))
        rows = q.order("created_at", desc=True).execute().data or []
    except Exception:
        return []
    return [_faculty_row(r) for r in rows]


def _owns_complaint(row, reporter_staff_id=None, teacher_id=None) -> bool:
    if not row:
        return False
    if reporter_staff_id is not None and row.get("reporter_staff_id") is not None:
        return int(row["reporter_staff_id"]) == int(reporter_staff_id)
    if teacher_id is not None and row.get("reporter_teacher_id") is not None:
        return int(row["reporter_teacher_id"]) == int(teacher_id)
    return False


def faculty_thread(complaint_id, reporter_staff_id=None, teacher_id=None):
    row = _complaint(complaint_id)
    if not _owns_complaint(row, reporter_staff_id, teacher_id):
        return []
    try:
        return supabase.table("complaint_messages").select("id,author_role,body,created_at").eq(
            "complaint_id", complaint_id
        ).order("created_at").execute().data or []
    except Exception:
        return []


def faculty_reply(complaint_id, body, *, reporter_staff_id=None, teacher_id=None, session_state=None):
    if _demo(session_state):
        return None, "Demo Mode cannot write production replies."
    row = _complaint(complaint_id)
    if not _owns_complaint(row, reporter_staff_id, teacher_id):
        return None, "You can only update your own complaints."
    text = (body or "").strip()
    if not text:
        return None, "Message is empty."
    store.insert("complaint_messages", {
        "complaint_id": complaint_id,
        "author_role": "faculty",
        "body": text[:4000],
    })
    if row.get("status") == "INFO_REQUIRED":
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "UNDER_REVIEW",
            "updated_at": _now().isoformat(),
        })
        _audit(
            actor_role="faculty", actor_ref=reporter_staff_id or teacher_id, action="COMPLAINT_UPDATED",
            complaint_id=complaint_id, student_id=row.get("student_id"),
            previous_status="INFO_REQUIRED", new_status="UNDER_REVIEW",
        )
    return True, "Additional information sent to administration."


def reporter_stats(reporter_staff_id=None, teacher_id=None):
    if reporter_staff_id is not None:
        rows = store.select("complaints", reporter_staff_id=int(reporter_staff_id)) or []
    elif teacher_id is not None:
        rows = store.select("complaints", reporter_teacher_id=int(teacher_id)) or []
    else:
        rows = []
    dismissed = sum(1 for r in rows if r.get("status") == "DISMISSED")
    valid = sum(1 for r in rows if r.get("status") in ("WARNING_ISSUED", "RESTRICTED", "BANNED", "ACTION_REQUIRED"))
    return {
        "submitted": len(rows),
        "dismissed": dismissed,
        "valid": valid,
        "open": sum(1 for r in rows if r.get("status") in ("SUBMITTED", "UNDER_REVIEW", "INFO_REQUIRED")),
        "repeated_false_reports": dismissed,
    }


def _complaint(complaint_id):
    if not installed() or not complaint_id:
        return None
    key = str(complaint_id).strip()
    if not key:
        return None
    try:
        rows = supabase.table("complaints").select("*").eq("complaint_id", key).limit(1).execute().data or []
        if rows:
            return rows[0]
        code = key.upper()
        rows = supabase.table("complaints").select("*").eq("complaint_code", code).limit(1).execute().data or []
        if rows:
            return rows[0]
        if code != key:
            rows = supabase.table("complaints").select("*").eq("complaint_code", key).limit(1).execute().data or []
        return rows[0] if rows else None
    except Exception:
        return None


def list_admin_complaints():
    if not installed():
        return []
    try:
        rows = supabase.table("complaints").select("*").order("created_at", desc=True).limit(300).execute().data or []
    except Exception:
        return []
    out = []
    for r in rows:
        stu = get_student_public(r["student_id"]) or {}
        staff = get_staff_public(r["reporter_staff_id"]) or {}
        teacher = get_teacher_public(r.get("reporter_teacher_id")) or {}
        stats = reporter_stats(
            reporter_staff_id=r.get("reporter_staff_id"),
            teacher_id=r.get("reporter_teacher_id"),
        )
        reporter = (
            staff.get("name") or staff.get("username")
            or teacher.get("name") or teacher.get("username")
            or r.get("reporter_staff_id") or r.get("reporter_teacher_id")
        )
        out.append({
            "complaintId": r["complaint_id"],
            "complaintCode": r["complaint_code"],
            "studentId": r["student_id"],
            "studentName": stu.get("name"),
            "studentAlias": r.get("student_alias_snapshot"),
            "reporter": reporter,
            "reporterStaffId": r.get("reporter_staff_id"),
            "reporterStats": stats,
            "category": r.get("category"),
            "severity": r.get("severity"),
            "status": r.get("status"),
            "hasEvidence": bool(r.get("has_evidence")),
            "requestedAction": r.get("requested_action"),
            "submittedAt": r.get("created_at"),
            "reviewStatus": P.faculty_status_label(r.get("status")),
        })
    return out


def admin_open(complaint_id, admin_staff_id, admin_role):
    if not P.can_review_complaints(admin_role):
        return None, "Only an administrator can open confidential complaint investigation."
    row = _complaint(complaint_id)
    if not row:
        return None, "Complaint not found."
    complaint_id = row["complaint_id"]
    if row.get("status") == "SUBMITTED":
        store.update("complaints", {"complaint_id": row["complaint_id"]}, {
            "status": "UNDER_REVIEW",
            "updated_at": _now().isoformat(),
        })
        row["status"] = "UNDER_REVIEW"
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="ADMIN_REVIEW_STARTED",
            complaint_id=row["complaint_id"], student_id=row.get("student_id"),
            previous_status="SUBMITTED", new_status="UNDER_REVIEW",
        )
        code = public_complaint_id(row)
        _notify_reporter(
            row, f"Complaint {code} under review",
            "Administration opened your complaint. The Complaint ID is unchanged.",
        )
    _audit(
        actor_role="administrator", actor_ref=admin_staff_id, action="COMPLAINT_VIEWED",
        complaint_id=complaint_id, student_id=row.get("student_id"),
    )
    student_id = int(row["student_id"])
    stu = get_student_public(student_id) or {}
    prev = []
    try:
        prev = supabase.table("complaints").select(
            "complaint_code,category,status,created_at,severity"
        ).eq("student_id", student_id).neq("complaint_id", complaint_id).order(
            "created_at", desc=True
        ).limit(20).execute().data or []
    except Exception:
        prev = []
    actions = store.select("moderation_actions", student_id=student_id) or []
    evidence = []
    try:
        evidence = supabase.table("complaint_evidence").select(
            "id,filename,mime,byte_size,sha256,note,added_by_role,created_at"
        ).eq("complaint_id", complaint_id).order("created_at").execute().data or []
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="COMPLAINT_VIEWED",
            complaint_id=complaint_id, student_id=student_id,
            metadata={"evidence_files": len(evidence), "access": "admin_metadata"},
        )
    except Exception:
        evidence = []
    messages = []
    try:
        messages = supabase.table("complaint_messages").select("id,author_role,body,created_at").eq(
            "complaint_id", complaint_id
        ).order("created_at").execute().data or []
    except Exception:
        messages = []
    mentorship = None
    if row.get("mentorship_id"):
        try:
            mrows = supabase.table("mentorships").select(
                "mentorship_id,student_alias,mentor_alias,status,started_at,counseling_goal"
            ).eq("mentorship_id", row["mentorship_id"]).limit(1).execute().data or []
            mentorship = mrows[0] if mrows else None
        except Exception:
            mentorship = None
    acct = student_snapshot(student_id)
    return {
        "complaint": row,
        "student": {"student_id": student_id, "name": stu.get("name")},
        "reporter": get_staff_public(row.get("reporter_staff_id")) or get_teacher_public(row.get("reporter_teacher_id")),
        "reporterStats": reporter_stats(
            reporter_staff_id=row.get("reporter_staff_id"),
            teacher_id=row.get("reporter_teacher_id"),
        ),
        "account": acct,
        "previousComplaints": prev,
        "previousActions": actions,
        "evidence": evidence,
        "messages": messages,
        "mentorship": mentorship,
    }, None


def request_information(complaint_id, admin_staff_id, admin_role, body, session_state=None):
    denied = P.faculty_cannot_execute("dismiss", admin_role) if not P.can_review_complaints(admin_role) else None
    if denied or not P.can_review_complaints(admin_role):
        return None, "Only an administrator can request additional information."
    if _demo(session_state):
        return None, "Demo Mode cannot write production reviews."
    row = _complaint(complaint_id)
    if not row:
        return None, "Complaint not found."
    text = (body or "").strip()
    if not text:
        return None, "Write the information you need."
    store.insert("complaint_messages", {
        "complaint_id": row["complaint_id"],
        "author_role": "administrator",
        "body": text[:4000],
    })
    store.update("complaints", {"complaint_id": row["complaint_id"]}, {
        "status": "INFO_REQUIRED",
        "updated_at": _now().isoformat(),
    })
    _audit(
        actor_role="administrator", actor_ref=admin_staff_id, action="ADMIN_REQUESTED_INFORMATION",
        complaint_id=row["complaint_id"], student_id=row.get("student_id"),
        previous_status=row.get("status"), new_status="INFO_REQUIRED", reason=text[:500],
    )
    if row.get("status") != "INFO_REQUIRED":
        code = public_complaint_id(row)
        _notify_reporter(
            row, f"Complaint {code} needs information",
            "Administration asked for more detail. The Complaint ID is unchanged.",
        )
    return True, "Faculty will see Additional Information Required — not your confidential notes."


def admin_decide(
    *,
    complaint_id,
    admin_staff_id,
    admin_role,
    action: str,
    reason: str,
    duration_hours=None,
    confirm_ban=False,
    session_state=None,
):
    blocked = P.faculty_cannot_execute(action, admin_role)
    if blocked:
        _audit(
            actor_role=admin_role, actor_ref=admin_staff_id, action="DENIED_EXECUTE",
            complaint_id=complaint_id, reason=blocked,
        )
        return None, blocked
    if not P.can_execute_moderation(admin_role):
        return None, "Only an authorized administrator can execute moderation."
    if _demo(session_state):
        return None, "Demo Mode cannot apply production bans or restrictions."
    if action not in P.EXECUTE_ACTIONS:
        return None, "Unknown action."
    if action == "ban" and not confirm_ban:
        return None, "Confirmation required. Ban Student and Request Ban are different permissions."
    note = (reason or "").strip()
    if len(note) < 8:
        return None, "Record a written reason for the audit log."
    row = _complaint(complaint_id)
    if not row:
        return None, "Complaint not found."
    complaint_id = row["complaint_id"]
    student_id = int(row["student_id"])
    prev = row.get("status")
    code = public_complaint_id(row)

    def _finish(new_status, message, *, notify_student=False, student_body=""):
        _notify_reporter(
            row, f"Complaint {code} updated",
            f"Status is now {P.faculty_status_label(new_status or prev)}. The Complaint ID is unchanged.",
        )
        if notify_student:
            _notify_event(
                role="student",
                recipient_id=student_id,
                title=f"Account update for complaint {code}",
                body=student_body or "Your account status was updated. Open Account status for details.",
            )
        return True, message

    store.insert("moderation_actions", {
        "complaint_id": complaint_id,
        "student_id": student_id,
        "admin_staff_id": admin_staff_id,
        "action": action,
        "duration_hours": duration_hours,
        "reason": note[:2000],
    })
    store.insert("complaint_reviews", {
        "complaint_id": complaint_id,
        "admin_staff_id": admin_staff_id,
        "decision": action,
        "reason": note[:2000],
    })

    until = None
    if duration_hours:
        until = (_now() + timedelta(hours=int(duration_hours))).isoformat()

    if action == "dismiss":
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "DISMISSED", "updated_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="COMPLAINT_DISMISSED",
            complaint_id=complaint_id, student_id=student_id,
            previous_status=prev, new_status="DISMISSED", reason=note,
        )
        return _finish("DISMISSED", "Complaint dismissed. No restriction was applied. The record is retained.")

    if action == "warning":
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "WARNING_ISSUED", "updated_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="WARNING_ISSUED",
            complaint_id=complaint_id, student_id=student_id,
            previous_status=prev, new_status="WARNING_ISSUED", reason=note,
        )
        return _finish(
            "WARNING_ISSUED",
            "Official warning recorded in the student's moderation history.",
            notify_student=True,
            student_body="An official warning was recorded. Open Account status for details.",
        )

    if action == "restrict":
        hours = int(duration_hours or 24)
        until = (_now() + timedelta(hours=hours)).isoformat()
        _set_status(student_id, "RESTRICTED", admin_staff_id=admin_staff_id, reason=note,
                    until_at=until, complaint_id=complaint_id, action_name="ACCOUNT_RESTRICTED")
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "RESTRICTED", "updated_at": _now().isoformat(),
        })
        return _finish(
            "RESTRICTED",
            f"Temporary restriction applied for {hours} hours.",
            notify_student=True,
            student_body="Your account is temporarily restricted. Open Account status for details.",
        )

    if action == "suspend":
        hours = int(duration_hours or 72)
        until = (_now() + timedelta(hours=hours)).isoformat()
        _set_status(student_id, "SUSPENDED", admin_staff_id=admin_staff_id, reason=note,
                    until_at=until, complaint_id=complaint_id, action_name="ACCOUNT_SUSPENDED")
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "RESTRICTED", "updated_at": _now().isoformat(),
        })
        return _finish(
            "RESTRICTED",
            f"Account suspended for {hours} hours. Login is blocked until then.",
            notify_student=True,
            student_body="Your account is suspended. Open Account status for details.",
        )

    if action == "ban":
        _set_status(student_id, "BANNED", admin_staff_id=admin_staff_id, reason=note,
                    until_at=None, complaint_id=complaint_id, action_name="ACCOUNT_BANNED")
        store.update("complaints", {"complaint_id": complaint_id}, {
            "status": "BANNED", "updated_at": _now().isoformat(),
        })
        return _finish(
            "BANNED",
            "Student account status is BANNED. The database record was not deleted.",
            notify_student=True,
            student_body="Your account is banned. You can appeal from Account status.",
        )

    if action == "restore":
        _set_status(student_id, "ACTIVE", admin_staff_id=admin_staff_id, reason=note,
                    until_at=None, complaint_id=complaint_id, action_name="BAN_REVOKED")
        return _finish(
            prev, "Account restored to ACTIVE.",
            notify_student=True,
            student_body="Your account was restored. Open Account status for details.",
        )

    if action == "reduce":
        hours = int(duration_hours or 24)
        until = (_now() + timedelta(hours=hours)).isoformat()
        _set_status(student_id, "RESTRICTED", admin_staff_id=admin_staff_id, reason=note,
                    until_at=until, complaint_id=complaint_id, action_name="ACCOUNT_RESTRICTED")
        return _finish(
            prev, f"Restriction reduced to {hours} hours.",
            notify_student=True,
            student_body="Your restriction was reduced. Open Account status for details.",
        )

    return None, "Unhandled action."


def submit_appeal(*, student_id, reason, explanation, evidence_note=None, complaint_id=None, session_state=None):
    if _demo(session_state):
        return None, "Demo Mode cannot submit production appeals."
    if not installed():
        return None, "Moderation schema is not installed."
    status, _, _ = effective_status(student_id)
    if not P.can_appeal(status):
        return None, "Appeals are available when your account is restricted, suspended, or banned."
    text = (reason or "").strip()
    if len(text) < 10:
        return None, "Explain why you are appealing."
    open_appeals = []
    try:
        open_appeals = supabase.table("student_appeals").select("id").eq("student_id", int(student_id)).eq(
            "status", "SUBMITTED"
        ).execute().data or []
    except Exception:
        open_appeals = []
    if open_appeals:
        return None, "You already have an appeal under review."
    row = store.insert("student_appeals", {
        "student_id": int(student_id),
        "complaint_id": complaint_id,
        "reason": text[:2000],
        "explanation": (explanation or "")[:4000],
        "evidence_note": (evidence_note or "")[:4000],
        "status": "SUBMITTED",
    })
    if not row:
        return None, "Could not save the appeal."
    _audit(
        actor_role="student", actor_ref=student_id, action="APPEAL_SUBMITTED",
        complaint_id=complaint_id, student_id=int(student_id), reason=text[:500],
    )
    try:
        from src.success.notify import notify
        notify(role="administrator", recipient_id="ops", title="New student appeal", body="Open Complaint Management to review the appeal.")
    except Exception:
        pass
    return row[0], "Appeal submitted to administration."


def list_appeals():
    if not installed():
        return []
    try:
        return supabase.table("student_appeals").select("*").order("created_at", desc=True).limit(200).execute().data or []
    except Exception:
        return []


def student_appeals(student_id):
    if not installed():
        return []
    try:
        return supabase.table("student_appeals").select(
            "id,reason,status,admin_note,created_at,reviewed_at"
        ).eq("student_id", int(student_id)).order("created_at", desc=True).execute().data or []
    except Exception:
        return []


def review_appeal(*, appeal_id, admin_staff_id, admin_role, decision: str, admin_note: str,
                  duration_hours=None, session_state=None):
    if not P.can_execute_moderation(admin_role):
        return None, "Only an authorized administrator can review appeals."
    if _demo(session_state):
        return None, "Demo Mode cannot write production appeal decisions."
    rows = store.select("student_appeals") or []
    row = next((r for r in rows if str(r.get("id")) == str(appeal_id)), None)
    if not row:
        try:
            found = supabase.table("student_appeals").select("*").eq("id", appeal_id).limit(1).execute().data or []
            row = found[0] if found else None
        except Exception:
            row = None
    if not row:
        return None, "Appeal not found."
    student_id = int(row["student_id"])
    note = (admin_note or "").strip() or decision

    def _ping(text):
        try:
            from src.success.notify import notify
            notify(role="student", recipient_id=student_id, title="Appeal reviewed", body=text)
        except Exception:
            pass

    if decision == "reject":
        store.update("student_appeals", {"id": row["id"]}, {
            "status": "REJECTED", "admin_note": note[:2000], "reviewed_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="APPEAL_REVIEWED",
            student_id=student_id, reason=note, metadata={"decision": "reject"},
        )
        msg = "Appeal rejected. Existing restriction is maintained."
        _ping(msg)
        return True, msg
    if decision == "accept" or decision == "restore":
        _set_status(student_id, "ACTIVE", admin_staff_id=admin_staff_id, reason=note,
                    action_name="BAN_REVOKED", complaint_id=row.get("complaint_id"))
        store.update("student_appeals", {"id": row["id"]}, {
            "status": "ACCEPTED", "admin_note": note[:2000], "reviewed_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="APPEAL_REVIEWED",
            student_id=student_id, reason=note, new_status="ACTIVE", metadata={"decision": "accept"},
        )
        msg = "Appeal accepted. Account restored."
        _ping(msg)
        return True, msg
    if decision == "reduce":
        hours = int(duration_hours or 24)
        until = (_now() + timedelta(hours=hours)).isoformat()
        _set_status(student_id, "RESTRICTED", admin_staff_id=admin_staff_id, reason=note,
                    until_at=until, action_name="ACCOUNT_RESTRICTED", complaint_id=row.get("complaint_id"))
        store.update("student_appeals", {"id": row["id"]}, {
            "status": "ACCEPTED", "admin_note": note[:2000], "reviewed_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="APPEAL_REVIEWED",
            student_id=student_id, reason=note, new_status="RESTRICTED", metadata={"decision": "reduce"},
        )
        msg = f"Appeal reviewed. Restriction reduced to {hours} hours."
        _ping(msg)
        return True, msg
    if decision == "maintain":
        store.update("student_appeals", {"id": row["id"]}, {
            "status": "REJECTED", "admin_note": note[:2000], "reviewed_at": _now().isoformat(),
        })
        _audit(
            actor_role="administrator", actor_ref=admin_staff_id, action="APPEAL_REVIEWED",
            student_id=student_id, reason=note, metadata={"decision": "maintain"},
        )
        msg = "Existing restriction maintained."
        _ping(msg)
        return True, msg
    return None, "Unknown appeal decision."


def audit_log(limit=80):
    if not installed():
        return []
    try:
        return supabase.table("moderation_audit_logs").select("*").order(
            "created_at", desc=True
        ).limit(limit).execute().data or []
    except Exception:
        return []


def warnings_for(student_id):
    rows = store.select("moderation_actions", student_id=int(student_id)) or []
    return [r for r in rows if r.get("action") == "warning"]
