"""Signed session tokens. Role/ids only — never passwords."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

from src.auth.session import SESSION_MINUTES
from src.database.config import get_secret


def _secret() -> bytes:
    value = get_secret("SESSION_SECRET") or get_secret("SUPABASE_KEY") or "classora-local-session"
    return hashlib.sha256(str(value).encode("utf-8")).digest()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def encode_token(session: dict) -> str:
    payload = {
        "v": 1,
        "role": session.get("user_role"),
        "login_type": session.get("login_type"),
        "demo": bool(session.get("demo_mode")),
        "demo_scenario": session.get("demo_scenario"),
        "exp": int(time.time()) + SESSION_MINUTES * 60,
        "teacher": session.get("teacher_data"),
        "student": session.get("student_data"),
        "staff": session.get("staff_data"),
        "merchant": session.get("merchant_data"),
    }
    body = _b64url(json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str).encode("utf-8"))
    signature = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def decode_token(token: str | None) -> dict | None:
    if not token or "." not in token:
        return None
    body, _, signature = token.partition(".")
    expected = _b64url(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        payload = json.loads(_b64url_decode(body).decode("utf-8"))
    except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if int(payload.get("exp") or 0) < int(time.time()):
        return None
    return {
        "is_logged_in": True,
        "user_role": payload.get("role"),
        "login_type": payload.get("login_type") or payload.get("role"),
        "demo_mode": bool(payload.get("demo")),
        "demo_scenario": payload.get("demo_scenario"),
        "teacher_data": payload.get("teacher"),
        "student_data": payload.get("student"),
        "staff_data": payload.get("staff"),
        "merchant_data": payload.get("merchant"),
    }
