"""Configurable verification policy. Face match is never PRESENT by itself."""

from __future__ import annotations

from datetime import datetime, timezone

INSTITUTION_ID = "default"

MODE_FACE_PLUS_QR = "FACE_PLUS_QR"
MODE_FACE_PLUS_CODE = "FACE_PLUS_CODE"
MODE_FACE_PLUS_QR_DEVICE = "FACE_PLUS_QR_AND_DEVICE"
MODE_FACE_PLUS_INAPP = "FACE_PLUS_INAPP"
MODE_FACE_ONLY = "FACE_ONLY"
MODES = (
    MODE_FACE_PLUS_QR,
    MODE_FACE_PLUS_CODE,
    MODE_FACE_PLUS_QR_DEVICE,
    MODE_FACE_PLUS_INAPP,
    MODE_FACE_ONLY,
)

SESSION_CREATED = "CREATED"
SESSION_ACTIVE = "ACTIVE"
SESSION_COMPLETED = "COMPLETED"
SESSION_EXPIRED = "EXPIRED"
SESSION_CANCELLED = "CANCELLED"

MARK_PENDING_FACE = "PENDING_FACE"
MARK_FACE_MATCHED = "FACE_MATCHED"
MARK_FACE_UNCERTAIN = "FACE_UNCERTAIN"
MARK_VERIFICATION_PENDING = "VERIFICATION_PENDING"
MARK_VERIFIED = "VERIFIED"
MARK_PRESENT = "PRESENT"
MARK_ABSENT = "ABSENT"
MARK_REJECTED = "REJECTED"
MARK_EXPIRED = "EXPIRED"
MARK_MANUAL_REVIEW = "MANUAL_REVIEW"
MARK_CANCELLED = "CANCELLED"

FACE_DETECTED = "FACE_DETECTED"
FACE_MATCHED = "FACE_MATCHED"
FACE_UNCERTAIN = "FACE_UNCERTAIN"
FACE_UNKNOWN = "FACE_UNKNOWN"

SOURCE_VERIFIED = "VERIFIED_AI"
SOURCE_MANUAL = "MANUAL"
SOURCE_LEGACY = "LEGACY"

METHOD_QR = "QR"
METHOD_CODE = "SECRET_CODE"
METHOD_INAPP = "IN_APP"
METHOD_DEVICE = "DEVICE"
METHOD_FACULTY = "FACULTY_REVIEW"

DEFAULT_SETTINGS = {
    "ai_attendance_enabled": True,
    "qr_verification_enabled": True,
    "secret_code_enabled": True,
    "voice_verification_enabled": False,
    "email_verification_enabled": False,
    "device_binding_enabled": True,
    "allow_image_upload": True,
    "verification_mode": MODE_FACE_PLUS_QR,
    "session_duration_minutes": 15,
    "qr_expiry_seconds": 45,
    "code_expiry_seconds": 90,
    "max_verification_attempts": 8,
    "uncertain_multiplier": 1.2,
    "institution_id": INSTITUTION_ID,
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value):
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=timezone.utc)


def normalize_settings(raw=None):
    cfg = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in cfg or value is None:
                continue
            try:
                if isinstance(cfg[key], bool):
                    cfg[key] = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes")
                elif isinstance(cfg[key], int):
                    cfg[key] = int(value)
                elif isinstance(cfg[key], float):
                    cfg[key] = float(value)
                else:
                    cfg[key] = type(cfg[key])(value)
            except (TypeError, ValueError):
                continue
    if cfg["verification_mode"] not in MODES:
        cfg["verification_mode"] = MODE_FACE_PLUS_QR
    cfg["session_duration_minutes"] = max(1, min(180, int(cfg["session_duration_minutes"])))
    cfg["qr_expiry_seconds"] = max(15, min(300, int(cfg["qr_expiry_seconds"])))
    cfg["code_expiry_seconds"] = max(30, min(600, int(cfg["code_expiry_seconds"])))
    cfg["max_verification_attempts"] = max(3, min(30, int(cfg["max_verification_attempts"])))
    cfg["uncertain_multiplier"] = max(1.0, min(2.0, float(cfg["uncertain_multiplier"])))
    return cfg


def requires_student_token(mode):
    return mode in (MODE_FACE_PLUS_QR, MODE_FACE_PLUS_QR_DEVICE)


def requires_secret_code(mode):
    return mode == MODE_FACE_PLUS_CODE


def requires_device(mode, device_binding_enabled):
    return mode == MODE_FACE_PLUS_QR_DEVICE or (device_binding_enabled and mode != MODE_FACE_ONLY)


def allows_faculty_finalize(mode):
    return mode == MODE_FACE_ONLY
