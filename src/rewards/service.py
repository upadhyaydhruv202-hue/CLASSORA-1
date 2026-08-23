"""Reward orchestration: policy, ledger, wallet, vouchers, RBAC, jobs."""

from __future__ import annotations

import hashlib
import logging
import secrets
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

from src.database.db import check_pass, hash_pass
from src.moderation.policy import ALLOWED_EVIDENCE_EXT, MAX_EVIDENCE_BYTES
from src.rewards import ledger as L
from src.rewards import policy as P
from src.success import notify as notifier
from src.success import store

logger = logging.getLogger("classora.rewards")

_TX = threading.Lock()
_RATES = defaultdict(deque)
_RATE_WINDOW = 3600
_RATE_LIMITS = {
    "submit": 20,
    "claim": 30,
    "redeem": 60,
    "award": 40,
}

VIEW_ROLES = ("student", "teacher", "faculty", "mentor", "counsellor", "administrator", "merchant")
STAFF_AWARD_ROLES = ("teacher", "faculty", "mentor", "counsellor", "administrator")
VERIFY_ROLES = ("teacher", "faculty", "mentor", "counsellor", "administrator")
APPROVE_ROLES = ("administrator",)
POLICY_ROLES = ("administrator",)
MERCHANT_MANAGE_ROLES = ("administrator",)
REDEEM_ROLES = ("administrator", "merchant")
REVERSE_ROLES = ("administrator",)


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


def institution_id():
    return P.INSTITUTION_ID


def actor_name(session):
    if not session:
        return ""
    if session.get("staff_data"):
        return session["staff_data"].get("username") or session["staff_data"].get("name") or ""
    if session.get("teacher_data"):
        return session["teacher_data"].get("username") or ""
    if session.get("student_data"):
        return session["student_data"].get("name") or ""
    if session.get("merchant_data"):
        return session["merchant_data"].get("name") or ""
    return session.get("user_role") or ""


def actor_id(session):
    if not session:
        return ""
    role = session.get("user_role")
    if role == "student":
        return str((session.get("student_data") or {}).get("student_id") or "")
    if role == "teacher":
        return str((session.get("teacher_data") or {}).get("teacher_id") or "")
    if role == "merchant":
        return str((session.get("merchant_data") or {}).get("merchant_id") or "")
    return str((session.get("staff_data") or {}).get("staff_id") or actor_name(session))


def audit(session, action, entity="", entity_id="", reason=""):
    store.insert("audit_events", {
        "actor": actor_name(session),
        "action": action,
        "entity": f"{entity}:{entity_id}" if entity_id else entity,
        "detail": (reason or "")[:400],
    })


def _rate(session, action):
    key = f"{session.get('user_role')}:{actor_id(session)}:{action}"
    now = time.time()
    bucket = _RATES[key]
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMITS.get(action, 30):
        return False
    bucket.append(now)
    return True


def get_settings():
    rows = store.select("reward_settings") or []
    raw = _jsonish(rows[0].get("settings"), {}) if rows else {}
    return P.normalize_settings(raw)


def save_settings(raw, session):
    cfg = P.normalize_settings(raw)
    existing = store.select("reward_settings") or []
    payload = {"settings": cfg, "updated_at": _iso()}
    if existing:
        store.update("reward_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        store.insert("reward_settings", {"id": 1, **payload})
    audit(session, "reward_settings_updated", "reward_settings")
    return cfg


def ensure_seed():
    if not (store.select("reward_categories") or []):
        for i, code in enumerate(P.CATEGORIES, 1):
            store.insert("reward_categories", {
                "institution_id": institution_id(),
                "code": code,
                "name": P.category_label(code),
                "active": True,
                "sort_order": i,
            })
    if not (store.select("reward_policies") or []):
        for category, typ, level, points, approval in P.DEFAULT_POLICIES:
            store.insert("reward_policies", {
                "institution_id": institution_id(),
                "version": 1,
                "category": category,
                "achievement_type": typ,
                "achievement_level": level,
                "points": int(points),
                "approval_required": bool(approval),
                "active": True,
                "valid_from": None,
                "valid_until": None,
                "source": "DEFAULT_CONFIGURATION",
                "created_at": _iso(),
            })
    if not (store.select("reward_settings") or []):
        store.insert("reward_settings", {"id": 1, "settings": P.normalize_settings({}), "updated_at": _iso()})


def list_categories():
    ensure_seed()
    rows = store.select("reward_categories") or []
    rows.sort(key=lambda row: int(row.get("sort_order") or 0))
    return [{
        "code": row.get("code"),
        "name": row.get("name") or P.category_label(row.get("code")),
        "active": bool(row.get("active", True)),
    } for row in rows]


def list_policies(active_only=True):
    ensure_seed()
    rows = store.select("reward_policies") or []
    out = []
    for row in rows:
        if active_only and not row.get("active", True):
            continue
        out.append(_policy_out(row))
    return out


def _policy_out(row):
    return {
        "id": row.get("id"),
        "category": row.get("category"),
        "achievementType": row.get("achievement_type"),
        "achievementLevel": row.get("achievement_level"),
        "points": int(row.get("points") or 0),
        "approvalRequired": bool(row.get("approval_required")),
        "active": bool(row.get("active", True)),
        "version": row.get("version") or 1,
        "validFrom": row.get("valid_from"),
        "validUntil": row.get("valid_until"),
        "source": row.get("source") or "CUSTOM",
    }


def upsert_policy(body, session):
    ensure_seed()
    category = str(body.get("category") or "").upper()
    if category not in P.CATEGORIES:
        return None, "Unknown reward category."
    points = _int(body.get("points"), None)
    if points is None or points < 0:
        return None, "Points must be a non-negative integer."
    row = {
        "institution_id": institution_id(),
        "version": _int(body.get("version"), 1),
        "category": category,
        "achievement_type": str(body.get("achievementType") or body.get("achievement_type") or "PARTICIPATION").upper(),
        "achievement_level": str(body.get("achievementLevel") or body.get("achievement_level") or "INSTITUTIONAL").upper(),
        "points": points,
        "approval_required": bool(body.get("approvalRequired") if body.get("approvalRequired") is not None else body.get("approval_required")),
        "active": True if body.get("active") is None else bool(body.get("active")),
        "valid_from": body.get("validFrom") or body.get("valid_from"),
        "valid_until": body.get("validUntil") or body.get("valid_until"),
        "source": "CUSTOM",
        "updated_at": _iso(),
    }
    pid = body.get("id")
    if pid:
        existing = store.select("reward_policies", id=_int(pid, pid)) or []
        if existing:
            # Version, do not rewrite history of issued rewards.
            row["version"] = int(existing[0].get("version") or 1) + 1
            store.update("reward_policies", {"id": existing[0].get("id")}, row)
            audit(session, "reward_policy_updated", "reward_policies", existing[0].get("id"))
            return _policy_out({**existing[0], **row, "id": existing[0].get("id")}), ""
    row["created_at"] = _iso()
    saved = store.insert("reward_policies", row)
    if not saved:
        return None, "Could not save the policy."
    audit(session, "reward_policy_created", "reward_policies", saved[0].get("id"))
    return _policy_out(saved[0]), ""


def recommend(category, achievement_type, achievement_level):
    ensure_seed()
    cfg = get_settings()
    return P.recommend_points(
        store.select("reward_policies") or [],
        str(category or "").upper(),
        str(achievement_type or "").upper(),
        str(achievement_level or "").upper(),
        cfg.get("policy_priority") or "HIGHEST",
    )


def _student_txns(student_id):
    return [row for row in (store.select("reward_transactions") or []) if _int(row.get("student_id")) == _int(student_id)]


def wallet_for(student_id):
    cfg = get_settings()
    return L.wallet(_student_txns(student_id), expiring_days=cfg.get("expiring_soon_days") or 7)


def _period_sum(rows, kind, since):
    total = 0
    for row in rows:
        if str(row.get("transaction_type")) != kind:
            continue
        if str(row.get("status") or "POSTED").upper() != "POSTED":
            continue
        ts = P.parse_ts(row.get("created_at"))
        if ts and ts >= since:
            total += abs(_int(row.get("points"), 0) or 0)
    return total


def _caps_ok(student_id, issuer, points, cfg):
    now = _now()
    rows = [r for r in _student_txns(student_id) if str(r.get("transaction_type")) == P.TX_EARN]
    if _period_sum(rows, P.TX_EARN, now - timedelta(days=1)) + points > cfg["daily_student_cap"]:
        return False, "Daily student earning cap would be exceeded."
    if _period_sum(rows, P.TX_EARN, now - timedelta(days=7)) + points > cfg["weekly_student_cap"]:
        return False, "Weekly student earning cap would be exceeded."
    if _period_sum(rows, P.TX_EARN, now - timedelta(days=30)) + points > cfg["monthly_student_cap"]:
        return False, "Monthly student earning cap would be exceeded."
    if issuer:
        issued = [r for r in (store.select("reward_transactions") or []) if str(r.get("issued_by") or "") == str(issuer)]
        if _period_sum(issued, P.TX_EARN, now - timedelta(days=1)) + points > cfg["daily_issuer_cap"]:
            return False, "Daily issuer award cap would be exceeded."
    return True, ""


def _insert_txn(**fields):
    payload = {
        "institution_id": institution_id(),
        "status": fields.get("status") or "POSTED",
        "created_at": _iso(),
        **fields,
    }
    saved = store.insert("reward_transactions", payload)
    return (saved or [None])[0]


def _earn(student_id, points, *, source_type, source_id, category, description, issued_by, approved_by, expires_days, metadata=None):
    cfg_days = expires_days
    expires = (_now() + timedelta(days=int(cfg_days))).isoformat()
    return _insert_txn(
        student_id=_int(student_id),
        transaction_type=P.TX_EARN,
        points=int(points),
        source_type=source_type,
        source_id=source_id,
        category=category,
        description=description,
        issued_by=issued_by or "",
        approved_by=approved_by or "",
        expires_at=expires,
        metadata=metadata or {},
    )


def _maybe_milestones(student_id):
    snap = wallet_for(student_id)
    earned = snap.get("totalEarned") or 0
    existing = {str(row.get("code")) for row in (store.select("reward_milestones") or []) if _int(row.get("student_id")) == _int(student_id)}
    for threshold in P.MILESTONES:
        code = f"PTS_{threshold}"
        if earned >= threshold and code not in existing:
            store.insert("reward_milestones", {
                "institution_id": institution_id(),
                "student_id": _int(student_id),
                "code": code,
                "points_threshold": threshold,
                "awarded_at": _iso(),
            })
            notifier.notify(
                role="student",
                recipient_id=student_id,
                title=f"{threshold} Reward Points milestone",
                body=f"You reached {threshold} lifetime Reward Points. Keep achieving.",
            )


def _maybe_badge(student_id, category, source_id):
    spec = P.BADGE_MAP.get(str(category or "").upper())
    if not spec:
        return
    title, family = spec
    code = f"BADGE_{category}"
    existing = [row for row in (store.select("reward_badges") or []) if _int(row.get("student_id")) == _int(student_id) and row.get("code") == code]
    if existing:
        return
    store.insert("reward_badges", {
        "institution_id": institution_id(),
        "student_id": _int(student_id),
        "code": code,
        "title": title,
        "family": family,
        "source_id": source_id,
        "awarded_at": _iso(),
    })


def _validate_evidence(evidence):
    data = _jsonish(evidence, {})
    url = str(data.get("url") or data.get("verificationUrl") or "").strip()
    note = str(data.get("note") or "")[:500]
    filename = str(data.get("filename") or "")
    mime = str(data.get("mime") or data.get("contentType") or "")
    digest = str(data.get("sha256") or "")
    size = _int(data.get("size"), 0) or 0
    if filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_EVIDENCE_EXT:
            return None, "INVALID_EVIDENCE"
    if size and size > MAX_EVIDENCE_BYTES:
        return None, "INVALID_EVIDENCE"
    return {"url": url, "note": note, "filename": filename, "mime": mime, "sha256": digest, "size": size}, ""


def _achievement_out(row, include_student=True):
    out = {
        "id": row.get("id"),
        "studentId": row.get("student_id") if include_student else None,
        "category": row.get("category"),
        "achievementType": row.get("achievement_type"),
        "achievementLevel": row.get("achievement_level"),
        "title": row.get("title"),
        "description": row.get("description"),
        "organization": row.get("organization"),
        "occurredAt": row.get("occurred_at"),
        "status": row.get("status"),
        "proposedPoints": row.get("proposed_points"),
        "awardedPoints": row.get("awarded_points"),
        "submittedBy": row.get("submitted_by"),
        "submittedRole": row.get("submitted_role"),
        "reviewReason": row.get("review_reason"),
        "evidence": _jsonish(row.get("evidence"), {}),
        "createdAt": row.get("created_at"),
        "reviewedAt": row.get("reviewed_at"),
    }
    return out


def submit_achievement(session, body):
    cfg = get_settings()
    if not cfg.get("rewards_enabled"):
        return None, "FEATURE_DISABLED"
    if not cfg.get("achievement_submission_enabled") and session.get("user_role") == "student":
        return None, "FEATURE_DISABLED"
    if not _rate(session, "submit"):
        return None, "RATE_LIMITED"
    role = session.get("user_role")
    if role == "student":
        student_id = _int((session.get("student_data") or {}).get("student_id"))
    else:
        student_id = _int(body.get("studentId") if body.get("studentId") is not None else body.get("student_id"))
    if student_id is None or student_id < 0:
        return None, "INVALID_STUDENT"
    category = str(body.get("category") or "").upper()
    if category not in P.CATEGORIES:
        return None, "UNKNOWN_CATEGORY"
    typ = str(body.get("achievementType") or body.get("achievement_type") or "PARTICIPATION").upper()
    level = str(body.get("achievementLevel") or body.get("achievement_level") or "INSTITUTIONAL").upper()
    title = str(body.get("title") or "").strip()[:160]
    if not title:
        return None, "TITLE_REQUIRED"
    occurred = body.get("occurredAt") or body.get("occurred_at") or _iso()
    cert = str(body.get("certificateId") or body.get("certificate_id") or "").strip()
    event_key = str(body.get("eventKey") or body.get("event_key") or title).strip()[:160]
    evidence, err = _validate_evidence(body.get("evidence"))
    if err:
        return None, err
    key = body.get("idempotencyKey") or body.get("idempotency_key") or P.duplicate_key(student_id, category, typ, event_key, occurred, cert)
    existing = [row for row in (store.select("reward_achievements") or []) if row.get("idempotency_key") == key]
    if existing:
        return _achievement_out(existing[0]), "DUPLICATE_REQUEST"
    rec = recommend(category, typ, level)
    points = int((rec or {}).get("points") or 0)
    if role != "student" and cfg.get("allow_manual_point_override") and body.get("points") not in (None, ""):
        override = _int(body.get("points"))
        if override is None or override < 0:
            return None, "INVALID_POINTS"
        if not str(body.get("overrideReason") or body.get("reason") or "").strip():
            return None, "OVERRIDE_REASON_REQUIRED"
        points = override
    if points <= 0:
        return None, "NO_MATCHING_POLICY"
    if role == "student":
        status = P.ACH_PENDING
    elif role == "administrator":
        status = P.ACH_APPROVED
    elif points > cfg["direct_award_max"] or (rec or {}).get("approvalRequired"):
        status = P.ACH_APPROVAL
    else:
        status = P.ACH_APPROVED
    row = {
        "institution_id": institution_id(),
        "student_id": student_id,
        "category": category,
        "achievement_type": typ,
        "achievement_level": level,
        "title": title,
        "description": str(body.get("description") or "")[:800],
        "organization": str(body.get("organization") or "")[:160],
        "occurred_at": occurred,
        "certificate_id": cert or None,
        "event_key": event_key,
        "evidence": evidence,
        "status": status,
        "proposed_points": points,
        "awarded_points": points if status == P.ACH_APPROVED else None,
        "policy_ids": (rec or {}).get("policyIds") or [],
        "submitted_by": actor_name(session),
        "submitted_role": role,
        "idempotency_key": key,
        "created_at": _iso(),
    }
    saved = store.insert("reward_achievements", row)
    if not saved:
        return None, "SAVE_FAILED"
    item = saved[0]
    audit(session, "reward_achievement_submitted", "reward_achievements", item.get("id"), title)
    if status == P.ACH_APPROVED:
        _finalize_award(item, session, points)
    else:
        notifier.notify(role="administrator", recipient_id="ops", title="Reward request pending", body=f"{title} is waiting for verification or approval.")
        if role == "student":
            notifier.notify(role="student", recipient_id=student_id, title="Achievement submitted", body=f"{title} is pending verification.")
    return _achievement_out(item), ""


def _finalize_award(achievement, session, points):
    cfg = get_settings()
    student_id = achievement.get("student_id")
    ok, msg = _caps_ok(student_id, achievement.get("submitted_by"), points, cfg)
    if not ok:
        store.update("reward_achievements", {"id": achievement.get("id")}, {"status": P.ACH_APPROVAL, "review_reason": msg})
        return None, msg
    txn = _earn(
        student_id,
        points,
        source_type="ACHIEVEMENT",
        source_id=achievement.get("id"),
        category=achievement.get("category"),
        description=achievement.get("title"),
        issued_by=achievement.get("submitted_by"),
        approved_by=actor_name(session),
        expires_days=cfg["point_expiry_days"],
        metadata={"policyIds": achievement.get("policy_ids") or []},
    )
    store.update("reward_achievements", {"id": achievement.get("id")}, {
        "status": P.ACH_APPROVED,
        "awarded_points": points,
        "reviewed_at": _iso(),
        "transaction_id": (txn or {}).get("id"),
    })
    _maybe_milestones(student_id)
    _maybe_badge(student_id, achievement.get("category"), achievement.get("id"))
    snap = wallet_for(student_id)
    notifier.notify(
        role="student",
        recipient_id=student_id,
        title="Achievement approved",
        body=f"{achievement.get('title')} verified. +{points} Reward Points. New balance: {snap.get('available')}.",
    )
    return txn, ""


def review_achievement(session, achievement_id, decision, reason=""):
    rows = store.select("reward_achievements", id=_int(achievement_id, achievement_id)) or []
    if not rows:
        rows = [row for row in (store.select("reward_achievements") or []) if str(row.get("id")) == str(achievement_id)]
    if not rows:
        return None, "NOT_FOUND"
    row = rows[0]
    cfg = get_settings()
    if not cfg.get("self_approval") and actor_name(session) and actor_name(session) == row.get("submitted_by"):
        return None, "SELF_APPROVAL_FORBIDDEN"
    wanted = str(decision or "").upper()
    if wanted in ("APPROVE", "VERIFY"):
        if row.get("status") == P.ACH_APPROVED:
            return _achievement_out(row), "DUPLICATE_REQUEST"
        if row.get("status") == P.ACH_REJECTED:
            return None, "REWARD_NOT_APPROVED"
        rec = recommend(row.get("category"), row.get("achievement_type"), row.get("achievement_level"))
        points = int(row.get("proposed_points") or (rec or {}).get("points") or 0)
        if row.get("status") == P.ACH_PENDING and points > cfg["direct_award_max"] and session.get("user_role") != "administrator":
            store.update("reward_achievements", {"id": row.get("id")}, {"status": P.ACH_APPROVAL, "review_reason": reason or "Needs higher approval."})
            audit(session, "reward_achievement_verified", "reward_achievements", row.get("id"))
            return _achievement_out({**row, "status": P.ACH_APPROVAL}), ""
        if session.get("user_role") not in APPROVE_ROLES and row.get("status") == P.ACH_APPROVAL:
            return None, "FORBIDDEN"
        _finalize_award(row, session, points)
        audit(session, "reward_achievement_approved", "reward_achievements", row.get("id"), reason)
        updated = store.select("reward_achievements", id=row.get("id")) or [row]
        return _achievement_out(updated[0]), ""
    if wanted == "REJECT":
        if not str(reason or "").strip():
            return None, "REASON_REQUIRED"
        store.update("reward_achievements", {"id": row.get("id")}, {
            "status": P.ACH_REJECTED,
            "review_reason": str(reason)[:400],
            "reviewed_at": _iso(),
            "awarded_points": 0,
        })
        notifier.notify(role="student", recipient_id=row.get("student_id"), title="Achievement rejected", body=str(reason)[:200])
        audit(session, "reward_achievement_rejected", "reward_achievements", row.get("id"), reason)
        return _achievement_out({**row, "status": P.ACH_REJECTED, "review_reason": reason}), ""
    if wanted in ("CHANGES", "REQUEST_CHANGES"):
        if not str(reason or "").strip():
            return None, "REASON_REQUIRED"
        store.update("reward_achievements", {"id": row.get("id")}, {"status": P.ACH_CHANGES, "review_reason": str(reason)[:400]})
        notifier.notify(role="student", recipient_id=row.get("student_id"), title="Changes requested", body=str(reason)[:200])
        return _achievement_out({**row, "status": P.ACH_CHANGES, "review_reason": reason}), ""
    return None, "UNKNOWN_DECISION"


def list_achievements(session, student_id=None, status="", limit=50, offset=0):
    rows = store.select("reward_achievements") or []
    role = session.get("user_role")
    if role == "student":
        sid = _int((session.get("student_data") or {}).get("student_id"))
        rows = [row for row in rows if _int(row.get("student_id")) == sid]
    elif student_id is not None:
        rows = [row for row in rows if _int(row.get("student_id")) == _int(student_id)]
    if status:
        rows = [row for row in rows if str(row.get("status")) == str(status)]
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    sliced = rows[int(offset): int(offset) + int(limit)]
    hide = role == "merchant"
    return [_achievement_out(row, include_student=not hide) for row in sliced], len(rows)


def list_transactions(session, student_id=None, limit=50, offset=0):
    rows = store.select("reward_transactions") or []
    role = session.get("user_role")
    if role == "student":
        sid = _int((session.get("student_data") or {}).get("student_id"))
        rows = [row for row in rows if _int(row.get("student_id")) == sid]
    elif student_id is not None:
        rows = [row for row in rows if _int(row.get("student_id")) == _int(student_id)]
    elif role == "merchant":
        return [], 0
    rows.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    sliced = rows[int(offset): int(offset) + int(limit)]
    return [{
        "id": row.get("id"),
        "studentId": row.get("student_id") if role != "student" else None,
        "type": row.get("transaction_type"),
        "points": P.signed_points(row.get("transaction_type"), row.get("points")),
        "category": row.get("category"),
        "description": row.get("description"),
        "status": row.get("status"),
        "issuedBy": row.get("issued_by"),
        "approvedBy": row.get("approved_by"),
        "expiresAt": row.get("expires_at"),
        "createdAt": row.get("created_at"),
        "sourceType": row.get("source_type"),
        "sourceId": row.get("source_id"),
    } for row in sliced], len(rows)


def reverse_transaction(session, txn_id, reason):
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    rows = store.select("reward_transactions", id=_int(txn_id, txn_id)) or []
    if not rows:
        rows = [row for row in (store.select("reward_transactions") or []) if str(row.get("id")) == str(txn_id)]
    if not rows:
        return None, "NOT_FOUND"
    original = rows[0]
    if str(original.get("transaction_type")) != P.TX_EARN:
        return None, "ONLY_EARN_REVERSIBLE"
    prior = [row for row in (store.select("reward_transactions") or []) if row.get("source_type") == "REVERSAL" and str(row.get("source_id")) == str(original.get("id"))]
    if prior:
        return None, "DUPLICATE_REQUEST"
    points = abs(_int(original.get("points"), 0) or 0)
    snap = wallet_for(original.get("student_id"))
    if (snap.get("available") or 0) < points:
        return None, "INSUFFICIENT_POINTS"
    txn = _insert_txn(
        student_id=original.get("student_id"),
        transaction_type=P.TX_REVERSAL,
        points=points,
        source_type="REVERSAL",
        source_id=original.get("id"),
        category=original.get("category"),
        description=f"Reversal: {reason}"[:200],
        issued_by=actor_name(session),
        approved_by=actor_name(session),
        metadata={"originalId": original.get("id")},
    )
    store.update("reward_transactions", {"id": original.get("id")}, {"reversed_at": _iso(), "reversal_reason": str(reason)[:400]})
    audit(session, "reward_reversed", "reward_transactions", original.get("id"), reason)
    return {"reversal": txn.get("id") if txn else None, "wallet": wallet_for(original.get("student_id"))}, ""


def adjust_points(session, student_id, points, reason):
    amount = _int(points)
    if amount is None or amount == 0:
        return None, "INVALID_POINTS"
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    if amount < 0 and wallet_for(student_id).get("available", 0) < abs(amount):
        return None, "INSUFFICIENT_POINTS"
    txn = _insert_txn(
        student_id=_int(student_id),
        transaction_type=P.TX_ADJUSTMENT,
        points=int(amount),
        source_type="ADJUSTMENT",
        category="OTHER",
        description=str(reason)[:200],
        issued_by=actor_name(session),
        approved_by=actor_name(session),
        expires_at=(_now() + timedelta(days=get_settings()["point_expiry_days"])).isoformat() if amount > 0 else None,
    )
    audit(session, "reward_adjustment", "reward_transactions", (txn or {}).get("id"), reason)
    return {"transaction": (txn or {}).get("id"), "wallet": wallet_for(student_id)}, ""


def list_merchants(session, include_inactive=False):
    rows = store.select("campus_merchants") or []
    if session.get("user_role") == "merchant":
        mid = _int((session.get("merchant_data") or {}).get("merchant_id"))
        rows = [row for row in rows if _int(row.get("id")) == mid]
    if not include_inactive:
        rows = [row for row in rows if row.get("active", True)]
    return [_merchant_out(row, session) for row in rows]


def _merchant_out(row, session=None):
    out = {
        "id": row.get("id"),
        "name": row.get("name"),
        "category": row.get("category"),
        "location": row.get("location"),
        "contact": row.get("contact") if session and session.get("user_role") in ("administrator", "merchant") else None,
        "active": bool(row.get("active", True)),
        "description": row.get("description"),
    }
    return out


def upsert_merchant(session, body):
    name = str(body.get("name") or "").strip()
    if not name:
        return None, "NAME_REQUIRED"
    category = str(body.get("category") or "OTHER").upper()
    if category not in P.MERCHANT_CATEGORIES:
        category = "OTHER"
    row = {
        "institution_id": institution_id(),
        "name": name,
        "category": category,
        "location": str(body.get("location") or "")[:160],
        "contact": str(body.get("contact") or "")[:160],
        "description": str(body.get("description") or "")[:400],
        "active": True if body.get("active") is None else bool(body.get("active")),
        "updated_at": _iso(),
    }
    code = str(body.get("accessCode") or body.get("access_code") or "").strip()
    if code:
        row["access_code_hash"] = hash_pass(code)
    mid = body.get("id")
    if mid:
        existing = store.select("campus_merchants", id=_int(mid, mid)) or []
        if existing:
            store.update("campus_merchants", {"id": existing[0].get("id")}, row)
            audit(session, "merchant_updated", "campus_merchants", existing[0].get("id"))
            return _merchant_out({**existing[0], **row, "id": existing[0].get("id")}, session), ""
    row["created_at"] = _iso()
    saved = store.insert("campus_merchants", row)
    if not saved:
        return None, "SAVE_FAILED"
    audit(session, "merchant_created", "campus_merchants", saved[0].get("id"))
    return _merchant_out(saved[0], session), ""


def merchant_login(merchant_id, access_code):
    rows = store.select("campus_merchants", id=_int(merchant_id, merchant_id)) or []
    if not rows:
        rows = [row for row in (store.select("campus_merchants") or []) if str(row.get("id")) == str(merchant_id)]
    if not rows or not rows[0].get("active", True):
        return None, "MERCHANT_NOT_AUTHORIZED"
    hashed = rows[0].get("access_code_hash")
    if not hashed or not access_code or not check_pass(str(access_code), hashed):
        return None, "UNAUTHORIZED"
    return {
        "merchant_id": rows[0].get("id"),
        "name": rows[0].get("name"),
        "category": rows[0].get("category"),
    }, ""


def upsert_offer(session, body):
    title = str(body.get("title") or "").strip()
    if not title:
        return None, "TITLE_REQUIRED"
    merchant_id = _int(body.get("merchantId") if body.get("merchantId") is not None else body.get("merchant_id"))
    if merchant_id is None:
        return None, "MERCHANT_REQUIRED"
    cost = _int(body.get("pointsCost") if body.get("pointsCost") is not None else body.get("points_cost"), None)
    if cost is None or cost < 0:
        return None, "INVALID_POINTS"
    discount_type = str(body.get("discountType") or body.get("discount_type") or "PERCENTAGE").upper()
    if discount_type not in P.DISCOUNT_TYPES:
        return None, "INVALID_DISCOUNT"
    value = _int(body.get("discountValue") if body.get("discountValue") is not None else body.get("discount_value"), 0) or 0
    row = {
        "institution_id": institution_id(),
        "merchant_id": merchant_id,
        "title": title,
        "description": str(body.get("description") or "")[:400],
        "discount_type": discount_type,
        "discount_value": int(value),
        "points_cost": int(cost),
        "min_purchase": _int(body.get("minimumPurchase") if body.get("minimumPurchase") is not None else body.get("min_purchase"), 0) or 0,
        "max_discount": _int(body.get("maximumDiscount") if body.get("maximumDiscount") is not None else body.get("max_discount"), 0) or 0,
        "redemption_limit": _int(body.get("redemptionLimit") if body.get("redemptionLimit") is not None else body.get("redemption_limit")),
        "per_student_limit": _int(body.get("perStudentLimit") if body.get("perStudentLimit") is not None else body.get("per_student_limit"), 1) or 1,
        "claimed_count": _int(body.get("claimed_count"), 0) or 0,
        "valid_from": body.get("validFrom") or body.get("valid_from"),
        "valid_until": body.get("validUntil") or body.get("valid_until"),
        "active": True if body.get("active") is None else bool(body.get("active")),
        "terms": str(body.get("terms") or "")[:800],
        "eligibility": _jsonish(body.get("eligibility"), {}),
        "updated_at": _iso(),
    }
    oid = body.get("id")
    if oid:
        existing = store.select("reward_offers", id=_int(oid, oid)) or []
        if existing:
            row["claimed_count"] = existing[0].get("claimed_count") or 0
            store.update("reward_offers", {"id": existing[0].get("id")}, row)
            audit(session, "reward_offer_updated", "reward_offers", existing[0].get("id"))
            return _offer_out({**existing[0], **row, "id": existing[0].get("id")}), ""
    row["created_at"] = _iso()
    row["claimed_count"] = 0
    saved = store.insert("reward_offers", row)
    if not saved:
        return None, "SAVE_FAILED"
    audit(session, "reward_offer_created", "reward_offers", saved[0].get("id"))
    return _offer_out(saved[0]), ""


def _offer_out(row, extra=None):
    merchant = {}
    mid = row.get("merchant_id")
    found = store.select("campus_merchants", id=_int(mid, mid)) or []
    if found:
        merchant = {"id": found[0].get("id"), "name": found[0].get("name"), "category": found[0].get("category")}
    data = {
        "id": row.get("id"),
        "merchantId": row.get("merchant_id"),
        "merchant": merchant,
        "title": row.get("title"),
        "description": row.get("description"),
        "discountType": row.get("discount_type"),
        "discountValue": row.get("discount_value"),
        "pointsCost": row.get("points_cost"),
        "minimumPurchase": row.get("min_purchase"),
        "maximumDiscount": row.get("max_discount"),
        "redemptionLimit": row.get("redemption_limit"),
        "perStudentLimit": row.get("per_student_limit"),
        "claimedCount": row.get("claimed_count") or 0,
        "validFrom": row.get("valid_from"),
        "validUntil": row.get("valid_until"),
        "active": bool(row.get("active", True)),
        "terms": row.get("terms"),
        "remaining": None if row.get("redemption_limit") in (None, "") else max(0, int(row.get("redemption_limit")) - int(row.get("claimed_count") or 0)),
    }
    if extra:
        data.update(extra)
    return data


def marketplace(session, category="", merchant_id="", q=""):
    cfg = get_settings()
    if not cfg.get("rewards_enabled"):
        return []
    now = _now()
    rows = store.select("reward_offers") or []
    out = []
    for row in rows:
        if not row.get("active", True):
            continue
        start = P.parse_ts(row.get("valid_from"))
        end = P.parse_ts(row.get("valid_until"))
        if start and now < start:
            continue
        if end and now > end:
            continue
        if row.get("redemption_limit") not in (None, "") and int(row.get("claimed_count") or 0) >= int(row.get("redemption_limit")):
            continue
        if category:
            merchants = store.select("campus_merchants", id=_int(row.get("merchant_id"), row.get("merchant_id"))) or []
            mcat = str((merchants or [{}])[0].get("category") or "").upper()
            if mcat != str(category).upper() and str(category).upper() not in str(row.get("title") or "").upper():
                continue
        if merchant_id and str(row.get("merchant_id")) != str(merchant_id):
            continue
        if q and q.lower() not in f"{row.get('title')} {row.get('description')}".lower():
            continue
        out.append(_offer_out(row))
    return out


def _hash_token(token):
    return hashlib.sha256(str(token).encode("utf-8")).hexdigest()


def claim_offer(session, offer_id, idempotency_key=""):
    cfg = get_settings()
    if not cfg.get("rewards_enabled"):
        return None, "FEATURE_DISABLED"
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "claim"):
        return None, "RATE_LIMITED"
    student_id = _int((session.get("student_data") or {}).get("student_id"))
    if student_id is None:
        return None, "INVALID_STUDENT"
    key = idempotency_key or f"claim:{student_id}:{offer_id}"
    with _TX:
        existing = [row for row in (store.select("reward_vouchers") or []) if row.get("idempotency_key") == key]
        if existing:
            return _voucher_out(existing[0], token=None), "DUPLICATE_REQUEST"
        offers = store.select("reward_offers", id=_int(offer_id, offer_id)) or []
        if not offers:
            offers = [row for row in (store.select("reward_offers") or []) if str(row.get("id")) == str(offer_id)]
        if not offers or not offers[0].get("active", True):
            return None, "VOUCHER_UNAVAILABLE"
        offer = offers[0]
        now = _now()
        start = P.parse_ts(offer.get("valid_from"))
        end = P.parse_ts(offer.get("valid_until"))
        if start and now < start:
            return None, "VOUCHER_UNAVAILABLE"
        if end and now > end:
            return None, "VOUCHER_EXPIRED"
        limit = offer.get("redemption_limit")
        claimed = int(offer.get("claimed_count") or 0)
        if limit not in (None, "") and claimed >= int(limit):
            return None, "VOUCHER_UNAVAILABLE"
        mine = [row for row in (store.select("reward_vouchers") or []) if _int(row.get("student_id")) == student_id and str(row.get("offer_id")) == str(offer.get("id")) and row.get("status") in (P.VOUCHER_ACTIVE, P.VOUCHER_REDEEMED)]
        per = int(offer.get("per_student_limit") or 1)
        if len(mine) >= per:
            return None, "VOUCHER_UNAVAILABLE"
        cost = int(offer.get("points_cost") or 0)
        snap = wallet_for(student_id)
        if (snap.get("available") or 0) < cost:
            return None, "INSUFFICIENT_POINTS"
        token = secrets.token_urlsafe(32)
        expires = now + timedelta(days=cfg["voucher_expiry_days"])
        voucher = {
            "institution_id": institution_id(),
            "offer_id": offer.get("id"),
            "merchant_id": offer.get("merchant_id"),
            "student_id": student_id,
            "token_hash": _hash_token(token),
            "token_hint": token[:4],
            "status": P.VOUCHER_ACTIVE,
            "points_cost": cost,
            "discount_type": offer.get("discount_type"),
            "discount_value": offer.get("discount_value"),
            "title": offer.get("title"),
            "claimed_at": _iso(now),
            "expires_at": expires.isoformat(),
            "idempotency_key": key,
            "created_at": _iso(now),
        }
        saved = store.insert("reward_vouchers", voucher)
        if not saved:
            return None, "REDEMPTION_FAILED"
        txn = _insert_txn(
            student_id=student_id,
            transaction_type=P.TX_REDEEM,
            points=cost,
            source_type="VOUCHER",
            source_id=saved[0].get("id"),
            category="REDEEM",
            description=f"Claimed {offer.get('title')}",
            issued_by=actor_name(session),
        )
        if not txn:
            store.update("reward_vouchers", {"id": saved[0].get("id")}, {"status": P.VOUCHER_CANCELLED, "cancel_reason": "Ledger write failed"})
            return None, "REDEMPTION_FAILED"
        store.update("reward_offers", {"id": offer.get("id")}, {"claimed_count": claimed + 1})
        store.update("reward_vouchers", {"id": saved[0].get("id")}, {"transaction_id": txn.get("id")})
        audit(session, "voucher_claimed", "reward_vouchers", saved[0].get("id"))
        notifier.notify(role="student", recipient_id=student_id, title="Voucher claimed", body=f"{offer.get('title')} is ready to redeem. Expires {expires.date().isoformat()}.")
        return _voucher_out(saved[0], token=token), ""


def _student_public_name(student_id):
    try:
        from src.database.db import get_student_public
        row = get_student_public(student_id) or {}
        return row.get("name")
    except Exception:
        return None


def _voucher_out(row, token=None, merchant_view=False):
    offer = (store.select("reward_offers", id=_int(row.get("offer_id"), row.get("offer_id"))) or [None])[0]
    merchant = (store.select("campus_merchants", id=_int(row.get("merchant_id"), row.get("merchant_id"))) or [None])[0]
    out = {
        "id": row.get("id"),
        "title": row.get("title") or (offer or {}).get("title"),
        "status": row.get("status"),
        "pointsCost": row.get("points_cost"),
        "discountType": row.get("discount_type") or (offer or {}).get("discount_type"),
        "discountValue": row.get("discount_value") if row.get("discount_value") is not None else (offer or {}).get("discount_value"),
        "claimedAt": row.get("claimed_at"),
        "expiresAt": row.get("expires_at"),
        "redeemedAt": row.get("redeemed_at"),
        "merchant": {"id": (merchant or {}).get("id"), "name": (merchant or {}).get("name")} if merchant else None,
        "terms": (offer or {}).get("terms"),
        "tokenHint": row.get("token_hint"),
    }
    if token:
        out["token"] = token
    if merchant_view:
        out["studentName"] = _student_public_name(row.get("student_id"))
        out["studentId"] = row.get("student_id")
    return out


def list_vouchers(session, status=""):
    rows = store.select("reward_vouchers") or []
    role = session.get("user_role")
    if role == "student":
        sid = _int((session.get("student_data") or {}).get("student_id"))
        rows = [row for row in rows if _int(row.get("student_id")) == sid]
    elif role == "merchant":
        mid = _int((session.get("merchant_data") or {}).get("merchant_id"))
        rows = [row for row in rows if _int(row.get("merchant_id")) == mid]
    if status:
        rows = [row for row in rows if str(row.get("status")) == str(status)]
    rows.sort(key=lambda row: str(row.get("claimed_at") or ""), reverse=True)
    return [_voucher_out(row, merchant_view=role in ("merchant", "administrator")) for row in rows]


def get_voucher(session, voucher_id):
    rows = store.select("reward_vouchers", id=_int(voucher_id, voucher_id)) or []
    if not rows:
        rows = [row for row in (store.select("reward_vouchers") or []) if str(row.get("id")) == str(voucher_id)]
    if not rows:
        return None, "NOT_FOUND"
    row = rows[0]
    role = session.get("user_role")
    if role == "student" and _int(row.get("student_id")) != _int((session.get("student_data") or {}).get("student_id")):
        return None, "FORBIDDEN"
    if role == "merchant" and _int(row.get("merchant_id")) != _int((session.get("merchant_data") or {}).get("merchant_id")):
        return None, "MERCHANT_NOT_AUTHORIZED"
    return _voucher_out(row, merchant_view=role in ("merchant", "administrator")), ""


def cancel_voucher(session, voucher_id, reason, refund=True):
    if not str(reason or "").strip():
        return None, "REASON_REQUIRED"
    with _TX:
        row, msg = _load_voucher(voucher_id)
        if not row:
            return None, msg
        if row.get("status") != P.VOUCHER_ACTIVE:
            return None, "VOUCHER_UNAVAILABLE"
        store.update("reward_vouchers", {"id": row.get("id")}, {
            "status": P.VOUCHER_REFUNDED if refund else P.VOUCHER_CANCELLED,
            "cancelled_at": _iso(),
            "cancel_reason": str(reason)[:400],
        })
        if refund:
            _insert_txn(
                student_id=row.get("student_id"),
                transaction_type=P.TX_REFUND,
                points=int(row.get("points_cost") or 0),
                source_type="VOUCHER",
                source_id=row.get("id"),
                category="REFUND",
                description=f"Refund: {reason}"[:200],
                issued_by=actor_name(session),
            )
            notifier.notify(role="student", recipient_id=row.get("student_id"), title="Voucher cancelled", body=f"Points refunded. {reason}"[:200])
        audit(session, "voucher_cancelled", "reward_vouchers", row.get("id"), reason)
        return {"ok": True, "wallet": wallet_for(row.get("student_id"))}, ""


def _load_voucher(voucher_id):
    rows = store.select("reward_vouchers", id=_int(voucher_id, voucher_id)) or []
    if not rows:
        rows = [row for row in (store.select("reward_vouchers") or []) if str(row.get("id")) == str(voucher_id)]
    if not rows:
        return None, "NOT_FOUND"
    return rows[0], ""


def _find_by_token(token):
    digest = _hash_token(token)
    for row in store.select("reward_vouchers") or []:
        if row.get("token_hash") == digest:
            return row
    return None


def validate_redemption(session, token):
    cfg = get_settings()
    if not cfg.get("merchant_redemption_enabled"):
        return None, "FEATURE_DISABLED"
    if not _rate(session, "redeem"):
        return None, "RATE_LIMITED"
    row = _find_by_token(token)
    if not row:
        return None, "NOT_FOUND"
    err = _redeem_guard(session, row)
    if err:
        return None, err
    return _voucher_out(row, merchant_view=True) | {"valid": True}, ""


def _redeem_guard(session, row):
    role = session.get("user_role")
    if role == "merchant":
        if _int(row.get("merchant_id")) != _int((session.get("merchant_data") or {}).get("merchant_id")):
            return "MERCHANT_NOT_AUTHORIZED"
    elif role != "administrator":
        return "FORBIDDEN"
    status = str(row.get("status") or "")
    if status == P.VOUCHER_REDEEMED:
        return "VOUCHER_ALREADY_REDEEMED"
    if status == P.VOUCHER_EXPIRED:
        return "VOUCHER_EXPIRED"
    if status == P.VOUCHER_CANCELLED:
        return "VOUCHER_CANCELLED"
    if status != P.VOUCHER_ACTIVE:
        return "VOUCHER_UNAVAILABLE"
    exp = P.parse_ts(row.get("expires_at"))
    if exp and _now() > exp:
        store.update("reward_vouchers", {"id": row.get("id"), "status": P.VOUCHER_ACTIVE}, {"status": P.VOUCHER_EXPIRED})
        return "VOUCHER_EXPIRED"
    return ""


def confirm_redemption(session, token):
    cfg = get_settings()
    if not cfg.get("merchant_redemption_enabled"):
        return None, "FEATURE_DISABLED"
    if not _rate(session, "redeem"):
        return None, "RATE_LIMITED"
    with _TX:
        row = _find_by_token(token)
        if not row:
            return None, "NOT_FOUND"
        err = _redeem_guard(session, row)
        if err:
            return None, err
        updated = store.update("reward_vouchers", {"id": row.get("id"), "status": P.VOUCHER_ACTIVE}, {
            "status": P.VOUCHER_REDEEMED,
            "redeemed_at": _iso(),
            "redeemed_by": actor_name(session),
        })
        if not updated:
            return None, "VOUCHER_ALREADY_REDEEMED"
        red = store.insert("voucher_redemptions", {
            "institution_id": institution_id(),
            "voucher_id": row.get("id"),
            "student_id": row.get("student_id"),
            "merchant_id": row.get("merchant_id"),
            "redeemed_by": actor_name(session),
            "redeemed_at": _iso(),
            "verification_method": "QR",
            "status": "CONFIRMED",
        })
        audit(session, "voucher_redeemed", "reward_vouchers", row.get("id"))
        notifier.notify(role="student", recipient_id=row.get("student_id"), title="Voucher redeemed", body=f"{row.get('title') or 'Voucher'} was redeemed.")
        return {
            "ok": True,
            "voucher": _voucher_out({**row, "status": P.VOUCHER_REDEEMED, "redeemed_at": _iso()}, merchant_view=True),
            "redemptionId": (red or [{}])[0].get("id"),
            "wallet": wallet_for(row.get("student_id")) if session.get("user_role") == "administrator" else None,
        }, ""


def _noticed(kind, entity_id, day):
    key = f"{kind}:{entity_id}:{day}"
    existing = [row for row in (store.select("reward_notice_log") or []) if row.get("notice_key") == key]
    if existing:
        return True
    store.insert("reward_notice_log", {"notice_key": key, "created_at": _iso()})
    return False


def tick_jobs(session=None):
    """Expiry, notifications, conservative automatic eligibility. Safe to call often."""
    cfg = get_settings()
    if not cfg.get("rewards_enabled"):
        return {"skipped": True}
    now = _now()
    expired_points = 0
    expired_vouchers = 0
    notices = 0
    auto = 0
    by_student = defaultdict(list)
    for row in store.select("reward_transactions") or []:
        by_student[_int(row.get("student_id"))].append(row)
    for sid, rows in by_student.items():
        if sid is None:
            continue
        due = L.expire_due(rows, now=now)
        for lot in due:
            pts = int(lot.get("points") or 0)
            if pts <= 0:
                continue
            _insert_txn(
                student_id=sid,
                transaction_type=P.TX_EXPIRE,
                points=pts,
                source_type="EXPIRE",
                source_id=lot.get("transactionId"),
                category="EXPIRE",
                description="Reward points expired",
                issued_by="system",
            )
            expired_points += pts
        snap = L.wallet(by_student[sid] + [], expiring_days=cfg.get("expiring_soon_days") or 7)
        # recompute after expire using fresh
        snap = wallet_for(sid)
        for lot in snap.get("expiringLots") or []:
            exp = P.parse_ts(lot.get("expiresAt"))
            if not exp:
                continue
            days = (exp.date() - now.date()).days
            if days in (cfg.get("notify_expiry_days") or [7, 3, 1]) and not _noticed("points", f"{sid}:{lot.get('transactionId')}", days):
                notifier.notify(role="student", recipient_id=sid, title="Reward Points expiring", body=f"{lot.get('points')} Reward Points expire in {days} day(s).")
                notices += 1
    for row in store.select("reward_vouchers") or []:
        if row.get("status") != P.VOUCHER_ACTIVE:
            continue
        exp = P.parse_ts(row.get("expires_at"))
        if exp and now > exp:
            store.update("reward_vouchers", {"id": row.get("id"), "status": P.VOUCHER_ACTIVE}, {"status": P.VOUCHER_EXPIRED})
            expired_vouchers += 1
            continue
        if exp:
            days = (exp.date() - now.date()).days
            if days in (cfg.get("notify_expiry_days") or [7, 3, 1]) and not _noticed("voucher", row.get("id"), days):
                notifier.notify(role="student", recipient_id=row.get("student_id"), title="Voucher expiring", body=f"{row.get('title') or 'A voucher'} expires in {days} day(s).")
                notices += 1
    if cfg.get("automatic_rewards_enabled"):
        auto = _auto_attendance(cfg)
    return {"expiredPoints": expired_points, "expiredVouchers": expired_vouchers, "notices": notices, "automaticAwards": auto}


def _auto_attendance(cfg):
    """Attendance improvement only — never uses dropout risk or counseling notes."""
    try:
        from src.cohort.service import load_classroom_bundle
        bundle = load_classroom_bundle()
    except Exception:
        return 0
    logs = bundle.get("attendance") or []
    if not logs:
        return 0
    now = _now()
    recent_from = now - timedelta(days=30)
    older_from = now - timedelta(days=60)
    by = defaultdict(lambda: {"recent": [0, 0], "older": [0, 0]})
    for row in logs:
        sid = _int(row.get("student_id"))
        ts = P.parse_ts(row.get("timestamp"))
        if sid is None or ts is None:
            continue
        present = 1 if row.get("is_present") else 0
        if ts >= recent_from:
            by[sid]["recent"][0] += present
            by[sid]["recent"][1] += 1
        elif ts >= older_from:
            by[sid]["older"][0] += present
            by[sid]["older"][1] += 1
    awarded = 0
    period = now.strftime("%Y-%m")
    fake_session = {"user_role": "administrator", "staff_data": {"username": "system"}}
    for sid, parts in by.items():
        r_p, r_n = parts["recent"]
        o_p, o_n = parts["older"]
        if r_n < 8 or o_n < 8:
            continue
        recent = 100.0 * r_p / r_n
        older = 100.0 * o_p / o_n
        if older >= 60 or recent < 75 or (recent - older) < 15:
            continue
        body = {
            "studentId": sid,
            "category": "ATTENDANCE",
            "achievementType": "IMPROVEMENT",
            "achievementLevel": "INSTITUTIONAL",
            "title": "Attendance improvement",
            "description": "Verified from CLASSORA attendance logs. This is recognition of improvement, not a change to any risk score.",
            "occurredAt": now.isoformat(),
            "eventKey": f"ATTENDANCE_IMPROVE:{period}",
            "idempotencyKey": P.duplicate_key(sid, "ATTENDANCE", "IMPROVEMENT", f"ATTENDANCE_IMPROVE:{period}", now.isoformat()),
        }
        _row, err = submit_achievement(fake_session, body)
        if err == "DUPLICATE_REQUEST":
            continue
        if not err:
            awarded += 1
    return awarded


def analytics(session):
    txns = store.select("reward_transactions") or []
    ach = store.select("reward_achievements") or []
    vouchers = store.select("reward_vouchers") or []
    redemptions = store.select("voucher_redemptions") or []
    issued = redeemed = expired = reversed_pts = 0
    by_cat = defaultdict(int)
    for row in txns:
        if str(row.get("status") or "POSTED").upper() != "POSTED":
            continue
        kind = row.get("transaction_type")
        pts = abs(_int(row.get("points"), 0) or 0)
        if kind == P.TX_EARN:
            issued += pts
            by_cat[row.get("category") or "OTHER"] += pts
        elif kind == P.TX_REDEEM:
            redeemed += pts
        elif kind == P.TX_EXPIRE:
            expired += pts
        elif kind == P.TX_REVERSAL:
            reversed_pts += pts
    students = {row.get("student_id") for row in txns if row.get("student_id") is not None}
    pending = sum(1 for row in ach if row.get("status") in (P.ACH_PENDING, P.ACH_APPROVAL))
    rejected = sum(1 for row in ach if row.get("status") == P.ACH_REJECTED)
    verified = sum(1 for row in ach if row.get("status") == P.ACH_APPROVED)
    active_v = sum(1 for row in vouchers if row.get("status") == P.VOUCHER_ACTIVE)
    redeemed_v = sum(1 for row in vouchers if row.get("status") == P.VOUCHER_REDEEMED)
    expired_v = sum(1 for row in vouchers if row.get("status") == P.VOUCHER_EXPIRED)
    merchants = defaultdict(int)
    for row in redemptions:
        merchants[row.get("merchant_id")] += 1
    top_merchant = None
    if merchants:
        mid = max(merchants, key=merchants.get)
        found = store.select("campus_merchants", id=_int(mid, mid)) or []
        top_merchant = {"id": mid, "name": (found or [{}])[0].get("name"), "redemptions": merchants[mid]}
    total_cat = sum(by_cat.values()) or 1
    concentration = None
    if by_cat:
        top_c, top_n = max(by_cat.items(), key=lambda item: item[1])
        share = round(100.0 * top_n / total_cat, 1)
        if share >= 90:
            concentration = f"Reward participation is heavily concentrated in {P.category_label(top_c)} achievements ({share}%)."
    return {
        "pointsIssued": issued,
        "pointsRedeemed": redeemed,
        "pointsExpired": expired,
        "pointsReversed": reversed_pts,
        "activeStudents": len(students),
        "achievementsSubmitted": len(ach),
        "verifiedAchievements": verified,
        "pendingApprovals": pending,
        "rejectedAchievements": rejected,
        "activeVouchers": active_v,
        "redeemedVouchers": redeemed_v,
        "expiredVouchers": expired_v,
        "redemptionRate": round(100.0 * redeemed_v / max(1, redeemed_v + active_v + expired_v), 1),
        "categoryShare": {k: round(100.0 * v / total_cat, 1) for k, v in by_cat.items()},
        "topMerchant": top_merchant,
        "concentrationNote": concentration,
        "educationLevel": get_settings().get("education_level"),
        "disclaimer": "Analytics describe observed reward activity. They do not claim that rewards caused academic or attendance change.",
    }


def student_summary(session):
    sid = _int((session.get("student_data") or {}).get("student_id"))
    if sid is None:
        return {"available": False}
    ensure_seed()
    snap = wallet_for(sid)
    return {
        "available": True,
        "wallet": snap,
        "recent": list_transactions(session, limit=5)[0],
    }


def public_rules():
    ensure_seed()
    policies = list_policies(active_only=True)
    grouped = defaultdict(list)
    for row in policies:
        grouped[row["category"]].append(f"{row['achievementType']} / {row['achievementLevel']} → {row['points']} points")
    return {
        "educationLevel": get_settings().get("education_level"),
        "categories": list_categories(),
        "levels": list(P.LEVELS),
        "positions": list(P.POSITIONS),
        "rules": [{"category": k, "items": v} for k, v in grouped.items()],
        "note": "Points are institutional recognition, not money. They cannot be withdrawn or converted to cash.",
    }


def leaderboard(session):
    cfg = get_settings()
    if not cfg.get("leaderboard_enabled"):
        return {"enabled": False, "rows": []}
    scores = defaultdict(int)
    for row in store.select("reward_transactions") or []:
        if str(row.get("transaction_type")) == P.TX_EARN and str(row.get("status") or "POSTED").upper() == "POSTED":
            scores[_int(row.get("student_id"))] += abs(_int(row.get("points"), 0) or 0)
    rows = []
    for sid, pts in sorted(scores.items(), key=lambda item: -item[1])[:20]:
        if sid is None:
            continue
        name = _student_public_name(sid) or f"Student {sid}"
        display = name[0] + "." if session.get("user_role") != "administrator" else name
        rows.append({"label": display, "points": pts})
    return {"enabled": True, "rows": rows}


def reconcile():
    issues = []
    for row in store.select("reward_vouchers") or []:
        if row.get("status") == P.VOUCHER_REDEEMED:
            reds = [r for r in (store.select("voucher_redemptions") or []) if str(r.get("voucher_id")) == str(row.get("id"))]
            if not reds:
                issues.append({"type": "redeemed_without_record", "voucherId": row.get("id")})
        if row.get("status") == P.VOUCHER_ACTIVE and row.get("transaction_id") is None:
            issues.append({"type": "claim_without_ledger", "voucherId": row.get("id")})
        exp = P.parse_ts(row.get("expires_at"))
        if row.get("status") == P.VOUCHER_ACTIVE and exp and _now() > exp:
            issues.append({"type": "expired_still_active", "voucherId": row.get("id")})
    for sid in {row.get("student_id") for row in (store.select("reward_transactions") or [])}:
        snap = wallet_for(sid)
        if (snap.get("available") or 0) < 0:
            issues.append({"type": "negative_balance", "studentId": sid})
    return {"ok": not issues, "issues": issues}
