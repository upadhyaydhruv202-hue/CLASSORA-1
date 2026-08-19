"""Pure moderation rules. Faculty request action; only administrator executes it."""

from __future__ import annotations

CATEGORIES = (
    "Abusive behavior",
    "Harassment",
    "Threatening behavior",
    "Repeated misconduct",
    "Inappropriate communication",
    "Misuse of platform",
    "Violation of counseling guidelines",
    "Other serious misconduct",
)

SEVERITIES = ("low", "medium", "high", "critical")

REQUESTED_ACTIONS = {
    "Warning": "warning",
    "Review": "review",
    "Temporary restriction": "temporary_restriction",
    "Student ID ban": "student_id_ban",
}

COMPLAINT_STATUSES = (
    "SUBMITTED",
    "UNDER_REVIEW",
    "INFO_REQUIRED",
    "DISMISSED",
    "ACTION_REQUIRED",
    "WARNING_ISSUED",
    "RESTRICTED",
    "BANNED",
)

ACCOUNT_STATUSES = ("ACTIVE", "RESTRICTED", "SUSPENDED", "BANNED")

FACULTY_STATUS_LABELS = {
    "SUBMITTED": "Submitted",
    "UNDER_REVIEW": "Under Review",
    "INFO_REQUIRED": "Additional Information Required",
    "DISMISSED": "Dismissed",
    "ACTION_REQUIRED": "Action Taken",
    "WARNING_ISSUED": "Action Taken",
    "RESTRICTED": "Action Taken",
    "BANNED": "Action Taken",
}

ALLOWED_EVIDENCE_MIME = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
    "application/pdf",
    "text/plain",
}

ALLOWED_EVIDENCE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"}
MAX_EVIDENCE_BYTES = 2 * 1024 * 1024

REPORTER_ROLES = ("faculty", "mentor", "counsellor", "teacher")
ADMIN_ROLE = "administrator"
EXECUTE_ACTIONS = frozenset({"dismiss", "warning", "restrict", "suspend", "ban", "restore", "reduce"})

LOGIN_BLOCKED = frozenset({"BANNED", "SUSPENDED"})
PARTICIPATION_BLOCKED = frozenset({"BANNED", "SUSPENDED", "RESTRICTED"})
APPEALABLE = frozenset({"BANNED", "SUSPENDED", "RESTRICTED"})

RESTRICT_PRESETS_HOURS = {
    "24 hours": 24,
    "3 days": 72,
    "7 days": 168,
}

FACULTY_PAYLOAD_FORBIDDEN = frozenset({
    "student_id",
    "name",
    "email",
    "phone",
    "username",
    "enrollment",
    "enrollment_number",
    "studentName",
    "studentEmail",
    "studentPhone",
    "adminNotes",
    "investigationNotes",
    "previousStatus",
    "face_embedding",
    "voice_embedding",
})


def faculty_status_label(status: str) -> str:
    return FACULTY_STATUS_LABELS.get(status or "", "Submitted")


def can_create_complaint(role: str | None) -> bool:
    return (role or "") in REPORTER_ROLES


def can_execute_moderation(role: str | None) -> bool:
    return (role or "") == ADMIN_ROLE


def can_review_complaints(role: str | None) -> bool:
    return (role or "") == ADMIN_ROLE


def can_view_protected_identity(role: str | None) -> bool:
    return (role or "") == ADMIN_ROLE


def login_allowed_for(status: str | None) -> bool:
    return (status or "ACTIVE") not in LOGIN_BLOCKED


def can_participate(status: str | None) -> bool:
    return (status or "ACTIVE") not in PARTICIPATION_BLOCKED


def can_appeal(status: str | None) -> bool:
    return (status or "ACTIVE") in APPEALABLE


def login_message(status: str | None) -> str:
    status = status or "ACTIVE"
    if status == "BANNED":
        return (
            "This student account is banned. Platform access is disabled. "
            "Historical records are preserved. You may submit an appeal from the student portal "
            "only after an administrator restores login, or contact campus administration."
        )
    if status == "SUSPENDED":
        return (
            "This student account is suspended. Sign-in is disabled until the restriction ends "
            "or an administrator restores access."
        )
    return ""


def account_banner(status: str | None, until_at=None) -> str | None:
    status = status or "ACTIVE"
    if status == "RESTRICTED":
        extra = f" Until {until_at}." if until_at else ""
        return f"Your account is temporarily restricted.{extra} Counseling and new mentorships are paused. You may appeal."
    if status == "SUSPENDED":
        return "Your account is suspended. You may submit an appeal."
    if status == "BANNED":
        return "Your account is banned. Historical records are kept. You may submit an appeal."
    return None


def validate_evidence(filename: str | None, mime: str | None, size: int | None) -> str | None:
    size = int(size or 0)
    if size <= 0:
        return "Evidence file is empty."
    if size > MAX_EVIDENCE_BYTES:
        return "Evidence must be 2 MB or smaller."
    mime = (mime or "").lower().strip()
    name = (filename or "").lower()
    ext = ""
    if "." in name:
        ext = "." + name.rsplit(".", 1)[-1]
    if mime and mime not in ALLOWED_EVIDENCE_MIME and ext not in ALLOWED_EVIDENCE_EXT:
        return "Evidence type not allowed. Use JPEG, PNG, WebP, PDF, or TXT."
    if not mime and ext not in ALLOWED_EVIDENCE_EXT:
        return "Evidence type not allowed. Use JPEG, PNG, WebP, PDF, or TXT."
    return None


def strip_faculty_payload(payload: dict | None) -> dict | None:
    """Never leak protected student identity or admin investigation notes to faculty."""
    if not payload:
        return payload
    return {k: v for k, v in payload.items() if k not in FACULTY_PAYLOAD_FORBIDDEN}


def faculty_cannot_execute(action: str, role: str | None) -> str | None:
    if action in EXECUTE_ACTIONS and not can_execute_moderation(role):
        return "Only an authorized administrator can execute this moderation action. Faculty may request review, not apply bans."
    return None
