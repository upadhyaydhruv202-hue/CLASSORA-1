"""Community orchestration: discovery, requests, membership, privacy, moderation."""

from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from urllib.parse import urlparse

from src.communities import detect
from src.communities import policy as P
from src.success import notify as notifier
from src.success import store

logger = logging.getLogger("classora.communities")

_RATES = defaultdict(deque)
_RATE_WINDOW = 3600
_RATE_LIMITS = {
    "request": 8,
    "post": 30,
    "comment": 60,
    "report": 20,
    "react": 120,
    "join": 40,
    "event": 20,
}

VIEW_ROLES = ("student", "administrator")
ADMIN_ROLES = ("administrator",)


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


def _bool(value, default=False):
    if value in (True, 1, "1", "true", "True", "yes"):
        return True
    if value in (False, 0, "0", "false", "False", "no"):
        return False
    return default


def institution_id():
    return P.INSTITUTION_ID


def actor_name(session):
    if not session:
        return ""
    if session.get("staff_data"):
        return session["staff_data"].get("username") or ""
    if session.get("student_data"):
        return f"student:{student_id(session)}"
    return session.get("user_role") or ""


def student_id(session):
    return _int((session.get("student_data") or {}).get("student_id"))


def _rate(session, action):
    key = f"{session.get('user_role')}:{student_id(session) or actor_name(session)}:{action}"
    now = time.time()
    bucket = _RATES[key]
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMITS.get(action, 30):
        return False
    bucket.append(now)
    return True


def audit(session, action, entity="", entity_id="", reason=""):
    store.insert("audit_events", {
        "actor": actor_name(session),
        "action": action,
        "entity": f"{entity}:{entity_id}" if entity_id else entity,
        "detail": (reason or "")[:400],
    })


def get_settings():
    rows = store.select("community_settings") or []
    raw = _jsonish(rows[0].get("settings"), {}) if rows else {}
    return P.normalize_settings(raw)


def save_settings(raw, session):
    if session.get("user_role") not in ADMIN_ROLES:
        return None, "FORBIDDEN"
    cfg = P.normalize_settings(raw)
    existing = store.select("community_settings") or []
    payload = {"settings": cfg, "updated_at": _iso()}
    if existing:
        store.update("community_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        store.insert("community_settings", {"id": 1, **payload})
    audit(session, "community_settings_updated", "community_settings")
    return cfg, ""


def ensure_seed():
    if not (store.select("community_settings") or []):
        store.insert("community_settings", {"id": 1, "settings": P.normalize_settings(), "updated_at": _iso()})
    if store.select("community_categories") or []:
        return
    for i, (code, name, order) in enumerate(P.DEFAULT_CATEGORIES, 1):
        store.insert("community_categories", {
            "institution_id": institution_id(),
            "code": code,
            "name": name,
            "active": True,
            "sort_order": order,
            "id": i,
        })


def _can_view(session):
    return session.get("user_role") in VIEW_ROLES


def _is_admin(session):
    return session.get("user_role") in ADMIN_ROLES


def _categories():
    rows = store.select("community_categories") or []
    rows = [row for row in rows if str(row.get("institution_id") or institution_id()) == institution_id()]
    rows.sort(key=lambda row: int(row.get("sort_order") or 0))
    return rows


def _category(code_or_id):
    needle = str(code_or_id or "").strip().upper()
    for row in _categories():
        if str(row.get("code") or "").upper() == needle or str(row.get("id")) == str(code_or_id):
            return row
    return None


def list_categories(session, active_only=True):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    rows = _categories()
    if active_only and not _is_admin(session):
        rows = [row for row in rows if _bool(row.get("active"), True)]
    return [{
        "id": row.get("id"),
        "code": row.get("code"),
        "name": row.get("name"),
        "active": _bool(row.get("active"), True),
        "sortOrder": row.get("sort_order"),
    } for row in rows], ""


def save_category(session, payload):
    if not _is_admin(session):
        return None, "FORBIDDEN"
    ensure_seed()
    code = str(payload.get("code") or payload.get("name") or "").strip().upper().replace(" ", "_")
    name = P.clean_text(payload.get("name") or code.title(), 40)
    if not code or not name:
        return None, "INVALID_CATEGORY"
    existing = _category(payload.get("id") or code)
    values = {
        "code": code[:30],
        "name": name,
        "active": _bool(payload.get("active"), True) if "active" in payload else True,
        "sort_order": _int(payload.get("sortOrder") or payload.get("sort_order"), 200),
        "updated_at": _iso(),
    }
    if existing:
        store.update("community_categories", {"id": existing.get("id")}, values)
        return {"id": existing.get("id"), **values}, ""
    saved = store.insert("community_categories", {
        "institution_id": institution_id(),
        **values,
    })
    return saved[0] if saved else values, ""


def _privacy_row(sid):
    if sid is None:
        return dict(P.PRIVACY_DEFAULTS)
    rows = store.select("community_privacy", student_id=sid) or []
    raw = rows[0] if rows else {}
    out = dict(P.PRIVACY_DEFAULTS)
    for key in P.PRIVACY_DEFAULTS:
        out[key] = _bool(raw.get(key), False)
    out["display_name"] = P.clean_text(raw.get("display_name") or "", 80)
    out["photo_url"] = P.safe_url(raw.get("photo_url") or "")
    out["course"] = P.clean_text(raw.get("course") or "", 80)
    out["semester"] = P.clean_text(raw.get("semester") or "", 40)
    out["skills"] = P.clean_text(raw.get("skills") or "", 200)
    out["bio"] = P.clean_text(raw.get("bio") or "", 280)
    out["portfolio"] = P.safe_url(raw.get("portfolio") or "")
    out["notify_pref"] = P.normalize_pref(raw.get("notify_pref"))
    out["interests"] = list(_jsonish(raw.get("interests"), []))
    return out


def _institutional_name(sid):
    try:
        from src.database.config import is_supabase_configured
        from src.database.db import get_student_public
        from src.database import local_store as local
        if is_supabase_configured():
            row = get_student_public(sid) or {}
            if row.get("name"):
                return str(row["name"])
        row = local.get_student(sid) or {}
        return str(row.get("name") or "")
    except Exception:
        return ""


def public_identity(target_sid, viewer_session, privacy=None):
    """Server-side identity. Hidden fields are omitted, not nulled."""
    sid = _int(target_sid)
    if sid is None:
        return {"studentId": None}
    privacy = privacy if privacy is not None else _privacy_row(sid)
    viewer = student_id(viewer_session)
    identity = {"studentId": sid}
    if viewer == sid:
        identity["self"] = True
    if privacy.get("show_name"):
        name = privacy.get("display_name") or _institutional_name(sid)
        if name:
            identity["name"] = name
    if privacy.get("show_photo") and privacy.get("photo_url"):
        identity["photoUrl"] = privacy["photo_url"]
    if privacy.get("show_department") and privacy.get("course"):
        identity["course"] = privacy["course"]
    if privacy.get("show_semester") and privacy.get("semester"):
        identity["semester"] = privacy["semester"]
    if privacy.get("show_skills") and privacy.get("skills"):
        identity["skills"] = privacy["skills"]
    if privacy.get("show_bio") and privacy.get("bio"):
        identity["bio"] = privacy["bio"]
    if privacy.get("show_portfolio") and privacy.get("portfolio"):
        identity["portfolio"] = privacy["portfolio"]
    return identity


def get_privacy(session):
    sid = student_id(session)
    if sid is None:
        return None, "FORBIDDEN"
    ensure_seed()
    row = _privacy_row(sid)
    return {
        "studentId": sid,
        "showName": row["show_name"],
        "showPhoto": row["show_photo"],
        "showDepartment": row["show_department"],
        "showSemester": row["show_semester"],
        "showSkills": row["show_skills"],
        "showBio": row["show_bio"],
        "showPortfolio": row["show_portfolio"],
        "displayName": row["display_name"],
        "photoUrl": row["photo_url"],
        "course": row["course"],
        "semester": row["semester"],
        "skills": row["skills"],
        "bio": row["bio"],
        "portfolio": row["portfolio"],
        "notifyPref": row["notify_pref"],
        "interests": row["interests"],
        "preview": public_identity(sid, session, row),
    }, ""


def save_privacy(session, payload):
    sid = student_id(session)
    if sid is None:
        return None, "FORBIDDEN"
    if payload.get("studentId") not in (None, "", sid) and _int(payload.get("studentId")) != sid:
        return None, "FORBIDDEN"
    ensure_seed()
    current = _privacy_row(sid)
    values = {
        "student_id": sid,
        "show_name": _bool(payload.get("showName", payload.get("show_name")), current["show_name"]),
        "show_photo": _bool(payload.get("showPhoto", payload.get("show_photo")), current["show_photo"]),
        "show_department": _bool(payload.get("showDepartment", payload.get("show_department")), current["show_department"]),
        "show_semester": _bool(payload.get("showSemester", payload.get("show_semester")), current["show_semester"]),
        "show_skills": _bool(payload.get("showSkills", payload.get("show_skills")), current["show_skills"]),
        "show_bio": _bool(payload.get("showBio", payload.get("show_bio")), current["show_bio"]),
        "show_portfolio": _bool(payload.get("showPortfolio", payload.get("show_portfolio")), current["show_portfolio"]),
        "display_name": P.clean_text(payload.get("displayName") or payload.get("display_name") or current["display_name"], 80),
        "photo_url": P.safe_url(payload.get("photoUrl") or payload.get("photo_url") or current["photo_url"]),
        "course": P.clean_text(payload.get("course") or current["course"], 80),
        "semester": P.clean_text(payload.get("semester") or current["semester"], 40),
        "skills": P.clean_text(payload.get("skills") or current["skills"], 200),
        "bio": P.clean_text(payload.get("bio") or current["bio"], 280),
        "portfolio": P.safe_url(payload.get("portfolio") or current["portfolio"]),
        "notify_pref": P.normalize_pref(payload.get("notifyPref") or payload.get("notify_pref") or current["notify_pref"]),
        "interests": payload.get("interests") if isinstance(payload.get("interests"), list) else current["interests"],
        "updated_at": _iso(),
    }
    existing = store.select("community_privacy", student_id=sid) or []
    if existing:
        store.update("community_privacy", {"id": existing[0].get("id")}, values)
    else:
        store.insert("community_privacy", values)
    return get_privacy(session)[0], ""


def _communities():
    return [
        row for row in (store.select("communities") or [])
        if str(row.get("institution_id") or institution_id()) == institution_id()
    ]


def _community(community_id):
    return next((row for row in _communities() if str(row.get("id")) == str(community_id) or row.get("slug") == community_id), None)


def _members(community_id, status="ACTIVE"):
    rows = store.select("community_members", community_id=_int(community_id, community_id)) or []
    if not rows:
        rows = [row for row in (store.select("community_members") or []) if str(row.get("community_id")) == str(community_id)]
    if status:
        rows = [row for row in rows if str(row.get("status") or "ACTIVE") == status]
    return rows


def _membership(community_id, sid):
    if sid is None:
        return None
    for row in _members(community_id, status=""):
        if _int(row.get("student_id")) == sid:
            return row
    return None


def _member_count(community_id):
    return len(_members(community_id, "ACTIVE"))


def _blocked_ids(sid):
    if sid is None:
        return set()
    rows = store.select("community_blocks") or []
    out = set()
    for row in rows:
        if _int(row.get("student_id")) == sid:
            out.add(_int(row.get("blocked_student_id")))
        if _int(row.get("blocked_student_id")) == sid:
            out.add(_int(row.get("student_id")))
    return {item for item in out if item is not None}


def _public_community(row, session, include_private=False):
    if not row:
        return None
    cat = _category(row.get("category_id") or row.get("category_code"))
    sid = student_id(session)
    mine = _membership(row.get("id"), sid)
    status = str(row.get("status") or "")
    visible = status in P.VISIBLE_STATUSES or (mine and str(mine.get("status")) == "ACTIVE") or _is_admin(session)
    if not visible:
        return None
    out = {
        "id": row.get("id"),
        "name": row.get("name"),
        "slug": row.get("slug"),
        "category": (cat or {}).get("name") or row.get("category_name") or "",
        "categoryCode": (cat or {}).get("code") or row.get("category_code") or "",
        "description": row.get("description") or "",
        "memberCount": _member_count(row.get("id")),
        "status": status,
        "tags": list(_jsonish(row.get("tags"), [])),
        "createdAt": row.get("created_at"),
        "joined": bool(mine and str(mine.get("status")) == "ACTIVE"),
        "role": (mine or {}).get("role") if mine and str(mine.get("status")) == "ACTIVE" else "",
    }
    if include_private:
        out["purpose"] = row.get("purpose") or ""
        out["rules"] = row.get("rules") or P.DEFAULT_RULES
        out["canPost"] = bool(mine and str(mine.get("status")) == "ACTIVE" and status == "ACTIVE")
        out["canModerate"] = bool(_is_admin(session) or (mine and mine.get("role") in {"MODERATOR", "COMMUNITY_ADMIN"} and str(mine.get("status")) == "ACTIVE"))
        out["canAdmin"] = bool(_is_admin(session) or (mine and mine.get("role") == "COMMUNITY_ADMIN" and str(mine.get("status")) == "ACTIVE"))
    return out


def list_communities(session, payload=None):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    payload = payload or {}
    q = str(payload.get("q") or payload.get("search") or "").strip().lower()
    category = str(payload.get("category") or "").strip().upper()
    mine = _bool(payload.get("mine"), False)
    offset = max(0, _int(payload.get("offset"), 0) or 0)
    limit = max(1, min(50, _int(payload.get("limit"), 20) or 20))
    sid = student_id(session)
    rows = []
    for row in _communities():
        pub = _public_community(row, session)
        if not pub:
            continue
        if pub["status"] not in P.VISIBLE_STATUSES and not pub.get("joined") and not _is_admin(session):
            continue
        if category and pub["categoryCode"] != category:
            continue
        if mine and not pub.get("joined"):
            continue
        blob = " ".join([pub["name"], pub["description"], pub["category"], " ".join(pub["tags"])]).lower()
        if q and q not in blob:
            continue
        rows.append(pub)
    rows.sort(key=lambda item: (-item["memberCount"], item["name"] or ""))
    return {
        "communities": rows[offset:offset + limit],
        "total": len(rows),
        "offset": offset,
        "limit": limit,
    }, ""


def get_community(session, community_id):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    row = _community(community_id)
    if not row:
        return None, "NOT_FOUND"
    pub = _public_community(row, session, include_private=True)
    if not pub:
        return None, "NOT_FOUND"
    return pub, ""


def similar_communities(session, payload):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    name = P.clean_text(payload.get("name") or "", 80)
    description = P.clean_text(payload.get("description") or "", 800)
    cat = _category(payload.get("category") or payload.get("categoryCode") or payload.get("category_id"))
    matches = detect.find_matches(
        name,
        (cat or {}).get("code") or "",
        description,
        [_enriched(row) for row in _communities()],
        get_settings(),
    )
    return {"matches": matches, "hasNearDuplicate": any(m["flag"] == "NEAR_DUPLICATE" for m in matches)}, ""


def _enriched(row):
    cat = _category(row.get("category_id") or row.get("category_code"))
    return {
        **row,
        "category_code": (cat or {}).get("code") or row.get("category_code"),
        "category_name": (cat or {}).get("name") or "",
    }


def create_request(session, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "request"):
        return None, "RATE_LIMITED"
    ensure_seed()
    sid = student_id(session)
    cfg = get_settings()
    if not cfg.get("enabled"):
        return None, "FEATURE_DISABLED"
    name = P.clean_text(payload.get("name") or "", cfg["max_name"])
    description = P.clean_text(payload.get("description") or "", cfg["max_description"])
    purpose = P.clean_text(payload.get("purpose") or "", 400)
    reason = P.clean_text(payload.get("reason") or "", 400)
    rules = P.clean_text(payload.get("rules") or P.DEFAULT_RULES, 1200)
    tags = [P.clean_text(str(t), 24) for t in (payload.get("tags") or []) if str(t).strip()][:8]
    cat = _category(payload.get("category") or payload.get("categoryCode") or payload.get("category_id"))
    if not name or not description or not reason or not cat or not _bool(cat.get("active"), True):
        return None, "INVALID_REQUEST"
    matches = detect.find_matches(name, cat.get("code"), description, [_enriched(row) for row in _communities()], cfg)
    if payload.get("previewOnly") or payload.get("preview_only"):
        return {"preview": True, "matches": matches, "hasNearDuplicate": any(m["flag"] == "NEAR_DUPLICATE" for m in matches)}, ""
    if matches and not _bool(payload.get("continueDespiteDuplicates") or payload.get("continue_despite_duplicates"), False):
        return {
            "blocked": True,
            "matches": matches,
            "message": f"A similar {matches[0]['name']} community already exists.",
        }, "POTENTIAL_DUPLICATE"
    saved = store.insert("community_requests", {
        "institution_id": institution_id(),
        "requested_name": name,
        "category_id": cat.get("id"),
        "category_code": cat.get("code"),
        "description": description,
        "purpose": purpose,
        "reason": reason,
        "rules": rules,
        "tags": tags,
        "expected_members": P.clean_text(payload.get("expectedMembers") or payload.get("expected_members") or "", 80),
        "banner_url": P.safe_url(payload.get("bannerUrl") or payload.get("banner_url") or ""),
        "requested_by": sid,
        "status": "PENDING",
        "duplicate_flag": bool(matches),
        "duplicate_matches": matches,
        "created_at": _iso(),
        "updated_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    notifier.notify(role="administrator", recipient_id="ops", title="Community request", body=f"A student requested '{name}'.")
    audit(session, "community_request_created", "community_requests", saved[0].get("id"))
    return _public_request(saved[0], session), ""


def _public_request(row, session):
    cat = _category(row.get("category_id") or row.get("category_code"))
    out = {
        "id": row.get("id"),
        "name": row.get("requested_name"),
        "category": (cat or {}).get("name") or "",
        "categoryCode": (cat or {}).get("code") or row.get("category_code"),
        "description": row.get("description"),
        "purpose": row.get("purpose"),
        "reason": row.get("reason"),
        "rules": row.get("rules"),
        "tags": list(_jsonish(row.get("tags"), [])),
        "status": row.get("status"),
        "duplicateFlag": _bool(row.get("duplicate_flag"), False),
        "matches": list(_jsonish(row.get("duplicate_matches"), [])),
        "reviewReason": row.get("review_reason") or "",
        "createdAt": row.get("created_at"),
        "requestedBy": row.get("requested_by") if _is_admin(session) or student_id(session) == _int(row.get("requested_by")) else None,
    }
    return out


def list_requests(session):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    sid = student_id(session)
    rows = store.select("community_requests") or []
    out = []
    for row in rows:
        if not _is_admin(session) and _int(row.get("requested_by")) != sid:
            continue
        out.append(_public_request(row, session))
    out.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    return out, ""


def update_request(session, request_id, payload):
    row = next((item for item in (store.select("community_requests") or []) if str(item.get("id")) == str(request_id)), None)
    if not row:
        return None, "NOT_FOUND"
    if student_id(session) != _int(row.get("requested_by")):
        return None, "FORBIDDEN"
    if str(row.get("status")) != "CHANGES_REQUESTED":
        return None, "NOT_EDITABLE"
    values = {
        "requested_name": P.clean_text(payload.get("name") or row.get("requested_name"), 80),
        "description": P.clean_text(payload.get("description") or row.get("description"), 800),
        "purpose": P.clean_text(payload.get("purpose") or row.get("purpose"), 400),
        "reason": P.clean_text(payload.get("reason") or row.get("reason"), 400),
        "rules": P.clean_text(payload.get("rules") or row.get("rules") or P.DEFAULT_RULES, 1200),
        "expected_members": P.clean_text(payload.get("expectedMembers") or payload.get("expected_members") or row.get("expected_members") or "", 80),
        "status": "PENDING",
        "updated_at": _iso(),
    }
    cat = _category(payload.get("category") or payload.get("categoryCode") or row.get("category_code"))
    if cat:
        values["category_id"] = cat.get("id")
        values["category_code"] = cat.get("code")
        values["duplicate_matches"] = detect.find_matches(values["requested_name"], cat.get("code"), values["description"], [_enriched(c) for c in _communities()], get_settings())
        values["duplicate_flag"] = bool(values["duplicate_matches"])
    store.update("community_requests", {"id": row.get("id")}, values)
    fresh = next((item for item in (store.select("community_requests") or []) if str(item.get("id")) == str(request_id)), {**row, **values})
    return _public_request(fresh, session), ""


def _unique_slug(name):
    base = P.slugify(name)
    used = {str(row.get("slug") or "") for row in _communities()}
    if base not in used:
        return base
    i = 2
    while f"{base}-{i}" in used:
        i += 1
    return f"{base}-{i}"


def review_request(session, request_id, payload):
    if not _is_admin(session):
        return None, "FORBIDDEN"
    row = next((item for item in (store.select("community_requests") or []) if str(item.get("id")) == str(request_id)), None)
    if not row:
        return None, "NOT_FOUND"
    decision = str(payload.get("decision") or "").strip().upper()
    reason = P.clean_text(payload.get("reason") or payload.get("reviewReason") or "", 400)
    if decision == "REJECT":
        store.update("community_requests", {"id": row.get("id")}, {
            "status": "REJECTED",
            "reviewed_by": actor_name(session),
            "reviewed_at": _iso(),
            "review_reason": reason or "Rejected",
            "updated_at": _iso(),
        })
        notifier.notify(role="student", recipient_id=row.get("requested_by"), title="Community request rejected", body=reason or "An administrator rejected this community request.")
        audit(session, "community_request_rejected", "community_requests", row.get("id"), reason)
        store.insert("community_moderation", {
            "action": "REQUEST_REJECTED",
            "actor": actor_name(session),
            "target_type": "REQUEST",
            "target_id": row.get("id"),
            "reason": reason,
            "created_at": _iso(),
        })
        return {"ok": True, "status": "REJECTED"}, ""
    if decision == "CHANGES":
        store.update("community_requests", {"id": row.get("id")}, {
            "status": "CHANGES_REQUESTED",
            "reviewed_by": actor_name(session),
            "reviewed_at": _iso(),
            "review_reason": reason or "Please update this request.",
            "updated_at": _iso(),
        })
        notifier.notify(role="student", recipient_id=row.get("requested_by"), title="Community request needs changes", body=reason or "Please update and resubmit.")
        audit(session, "community_request_changes", "community_requests", row.get("id"), reason)
        return {"ok": True, "status": "CHANGES_REQUESTED"}, ""
    if decision != "APPROVE":
        return None, "INVALID_DECISION"
    cat = _category(row.get("category_id") or row.get("category_code"))
    created = store.insert("communities", {
        "institution_id": institution_id(),
        "name": row.get("requested_name"),
        "slug": _unique_slug(row.get("requested_name")),
        "category_id": (cat or {}).get("id"),
        "category_code": (cat or {}).get("code"),
        "description": row.get("description"),
        "purpose": row.get("purpose"),
        "rules": row.get("rules") or P.DEFAULT_RULES,
        "tags": _jsonish(row.get("tags"), []),
        "status": "ACTIVE",
        "created_by": row.get("requested_by"),
        "approved_by": actor_name(session),
        "approved_at": _iso(),
        "created_at": _iso(),
        "updated_at": _iso(),
    })
    if not created:
        return None, "SAVE_FAILED"
    community = created[0]
    grant = _bool(payload.get("grantAdmin", payload.get("grant_admin")), True)
    store.insert("community_members", {
        "community_id": community.get("id"),
        "student_id": row.get("requested_by"),
        "role": "COMMUNITY_ADMIN" if grant else "MEMBER",
        "status": "ACTIVE",
        "joined_at": _iso(),
    })
    store.update("community_requests", {"id": row.get("id")}, {
        "status": "APPROVED",
        "reviewed_by": actor_name(session),
        "reviewed_at": _iso(),
        "review_reason": reason,
        "community_id": community.get("id"),
        "updated_at": _iso(),
    })
    notifier.notify(role="student", recipient_id=row.get("requested_by"), title="Community approved", body=f"{community.get('name')} is now active.")
    audit(session, "community_request_approved", "communities", community.get("id"), reason)
    store.insert("community_moderation", {
        "action": "REQUEST_APPROVED",
        "actor": actor_name(session),
        "community_id": community.get("id"),
        "target_type": "REQUEST",
        "target_id": row.get("id"),
        "reason": reason,
        "created_at": _iso(),
    })
    return {"ok": True, "status": "APPROVED", "community": _public_community(community, session, include_private=True)}, ""


def join(session, community_id):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "join"):
        return None, "RATE_LIMITED"
    sid = student_id(session)
    row = _community(community_id)
    if not row:
        return None, "NOT_FOUND"
    if str(row.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE"
    existing = _membership(row.get("id"), sid)
    if existing and str(existing.get("status")) == "ACTIVE":
        return {"ok": True, "alreadyJoined": True, "community": _public_community(row, session, True)}, ""
    if existing and str(existing.get("status")) == "SUSPENDED":
        return None, "MEMBER_SUSPENDED"
    cfg = get_settings()
    mine = [m for m in (store.select("community_members") or []) if _int(m.get("student_id")) == sid and str(m.get("status")) == "ACTIVE"]
    if len(mine) >= cfg["max_memberships"]:
        return None, "MEMBERSHIP_LIMIT"
    if existing:
        store.update("community_members", {"id": existing.get("id")}, {"status": "ACTIVE", "role": existing.get("role") or "MEMBER", "joined_at": _iso()})
    else:
        store.insert("community_members", {
            "community_id": row.get("id"),
            "student_id": sid,
            "role": "MEMBER",
            "status": "ACTIVE",
            "joined_at": _iso(),
        })
    return {"ok": True, "community": _public_community(row, session, True)}, ""


def leave(session, community_id):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    sid = student_id(session)
    row = _community(community_id)
    if not row:
        return None, "NOT_FOUND"
    existing = _membership(row.get("id"), sid)
    if not existing or str(existing.get("status")) != "ACTIVE":
        return {"ok": True, "alreadyLeft": True}, ""
    store.update("community_members", {"id": existing.get("id")}, {"status": "LEFT", "left_at": _iso()})
    return {"ok": True}, ""


def list_members(session, community_id, offset=0, limit=20):
    if not _can_view(session):
        return None, "FORBIDDEN"
    row = _community(community_id)
    pub = _public_community(row, session, True) if row else None
    if not pub:
        return None, "NOT_FOUND"
    blocked = _blocked_ids(student_id(session))
    members = []
    for item in _members(row.get("id"), "ACTIVE"):
        sid = _int(item.get("student_id"))
        if sid in blocked:
            continue
        identity = public_identity(sid, session)
        members.append({
            **identity,
            "role": item.get("role") or "MEMBER",
        })
    offset = max(0, _int(offset, 0) or 0)
    limit = max(1, min(50, _int(limit, 20) or 20))
    return {"members": members[offset:offset + limit], "total": len(members), "memberCount": _member_count(row.get("id"))}, ""


def _can_post(session, community):
    if str(community.get("status")) != "ACTIVE":
        return False
    mine = _membership(community.get("id"), student_id(session))
    return bool(mine and str(mine.get("status")) == "ACTIVE")


def _can_moderate(session, community):
    if _is_admin(session):
        return True
    mine = _membership(community.get("id"), student_id(session))
    return bool(mine and str(mine.get("status")) == "ACTIVE" and mine.get("role") in {"MODERATOR", "COMMUNITY_ADMIN"})


def create_post(session, community_id, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "post"):
        return None, "RATE_LIMITED"
    community = _community(community_id)
    if not community:
        return None, "NOT_FOUND"
    if str(community.get("status")) == "SUSPENDED":
        return None, "COMMUNITY_SUSPENDED"
    if str(community.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE"
    if not _can_post(session, community):
        return None, "FORBIDDEN"
    cfg = get_settings()
    kind = str(payload.get("kind") or "POST").strip().upper()
    if kind not in P.POST_KINDS:
        kind = "POST"
    if kind == "ANNOUNCEMENT" and not _can_moderate(session, community):
        return None, "FORBIDDEN"
    content = P.clean_text(payload.get("content") or "", cfg["max_post"])
    if not content:
        return None, "EMPTY_CONTENT"
    link = P.safe_url(payload.get("link") or "")
    options = [P.clean_text(str(opt), 80) for opt in (payload.get("options") or []) if str(opt).strip()][:6]
    if kind == "POLL" and len(options) < 2:
        return None, "INVALID_POLL"
    saved = store.insert("community_posts", {
        "community_id": community.get("id"),
        "author_student_id": student_id(session),
        "kind": kind,
        "content": content,
        "link": link,
        "options": options,
        "status": "ACTIVE",
        "created_at": _iso(),
        "updated_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    if kind == "ANNOUNCEMENT":
        _notify_members(community, "ANNOUNCEMENTS", "Community announcement", content[:160])
    return _public_post(saved[0], session, community), ""


def _notify_members(community, channel, title, body):
    for member in _members(community.get("id"), "ACTIVE"):
        pref = _privacy_row(_int(member.get("student_id"))).get("notify_pref") or "ALL"
        if pref == "NONE":
            continue
        if channel == "ANNOUNCEMENTS" and pref not in {"ALL", "ANNOUNCEMENTS"}:
            continue
        if channel == "EVENTS" and pref not in {"ALL", "EVENTS"}:
            continue
        notifier.notify(role="student", recipient_id=member.get("student_id"), title=title, body=body)


def _reaction_counts(post_id):
    rows = [row for row in (store.select("community_reactions") or []) if str(row.get("post_id")) == str(post_id)]
    counts = {key: 0 for key in P.REACTIONS}
    poll = defaultdict(int)
    for row in rows:
        kind = str(row.get("kind") or "")
        if kind in counts:
            counts[kind] += 1
        if kind == "POLL":
            extra = _jsonish(row.get("extra"), {})
            poll[str(extra.get("option"))] += 1
    return counts, dict(poll)


def _comment_count(post_id):
    return len([
        row for row in (store.select("community_comments") or [])
        if str(row.get("post_id")) == str(post_id) and str(row.get("status") or "ACTIVE") == "ACTIVE"
    ])


def _public_post(row, session, community=None):
    if str(row.get("status") or "ACTIVE") != "ACTIVE":
        return None
    author = _int(row.get("author_student_id"))
    if author in _blocked_ids(student_id(session)):
        return None
    counts, poll = _reaction_counts(row.get("id"))
    return {
        "id": row.get("id"),
        "communityId": row.get("community_id"),
        "kind": row.get("kind") or "POST",
        "content": row.get("content"),
        "link": row.get("link") or "",
        "options": list(_jsonish(row.get("options"), [])),
        "createdAt": row.get("created_at"),
        "author": public_identity(author, session),
        "reactions": counts,
        "pollCounts": poll,
        "commentCount": _comment_count(row.get("id")),
    }


def list_posts(session, community_id, offset=0, limit=20, kind=""):
    if not _can_view(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not _public_community(community, session):
        return None, "NOT_FOUND"
    rows = [row for row in (store.select("community_posts") or []) if str(row.get("community_id")) == str(community.get("id"))]
    if kind:
        rows = [row for row in rows if str(row.get("kind")) == str(kind).upper()]
    rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    posts = []
    for row in rows:
        pub = _public_post(row, session, community)
        if pub:
            posts.append(pub)
    offset = max(0, _int(offset, 0) or 0)
    limit = max(1, min(50, _int(limit, 20) or 20))
    return {"posts": posts[offset:offset + limit], "total": len(posts), "communityStatus": community.get("status")}, ""


def add_comment(session, community_id, post_id, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "comment"):
        return None, "RATE_LIMITED"
    community = _community(community_id)
    if not community or str(community.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE" if community else "NOT_FOUND"
    if str(community.get("status")) == "SUSPENDED":
        return None, "COMMUNITY_SUSPENDED"
    if not _can_post(session, community):
        return None, "FORBIDDEN"
    post = next((row for row in (store.select("community_posts") or []) if str(row.get("id")) == str(post_id) and str(row.get("community_id")) == str(community.get("id"))), None)
    if not post or str(post.get("status")) != "ACTIVE":
        return None, "NOT_FOUND"
    content = P.clean_text(payload.get("content") or "", get_settings()["max_comment"])
    if not content:
        return None, "EMPTY_CONTENT"
    saved = store.insert("community_comments", {
        "community_id": community.get("id"),
        "post_id": post.get("id"),
        "author_student_id": student_id(session),
        "content": content,
        "status": "ACTIVE",
        "created_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    return _public_comment(saved[0], session), ""


def _public_comment(row, session):
    if str(row.get("status") or "ACTIVE") != "ACTIVE":
        return None
    author = _int(row.get("author_student_id"))
    if author in _blocked_ids(student_id(session)):
        return None
    return {
        "id": row.get("id"),
        "postId": row.get("post_id"),
        "content": row.get("content"),
        "createdAt": row.get("created_at"),
        "author": public_identity(author, session),
    }


def list_comments(session, community_id, post_id, offset=0, limit=30):
    if not _can_view(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not _public_community(community, session):
        return None, "NOT_FOUND"
    rows = [
        row for row in (store.select("community_comments") or [])
        if str(row.get("post_id")) == str(post_id) and str(row.get("community_id")) == str(community.get("id"))
    ]
    rows.sort(key=lambda item: str(item.get("created_at") or ""))
    comments = [c for c in (_public_comment(row, session) for row in rows) if c]
    offset = max(0, _int(offset, 0) or 0)
    limit = max(1, min(50, _int(limit, 30) or 30))
    return {"comments": comments[offset:offset + limit], "total": len(comments)}, ""


def react(session, community_id, post_id, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "react"):
        return None, "RATE_LIMITED"
    community = _community(community_id)
    if not community or str(community.get("status")) != "ACTIVE" or not _can_post(session, community):
        return None, "FORBIDDEN" if community else "NOT_FOUND"
    post = next((row for row in (store.select("community_posts") or []) if str(row.get("id")) == str(post_id)), None)
    if not post or str(post.get("community_id")) != str(community.get("id")):
        return None, "NOT_FOUND"
    kind = P.normalize_reaction(payload.get("kind") or payload.get("reaction"))
    option = payload.get("option")
    sid = student_id(session)
    if option is not None:
        kind = "POLL"
        extra = {"option": _int(option, 0)}
    else:
        extra = {}
        if not kind:
            return None, "INVALID_REACTION"
    existing = [
        row for row in (store.select("community_reactions") or [])
        if str(row.get("post_id")) == str(post_id) and _int(row.get("student_id")) == sid and str(row.get("kind")) == kind
    ]
    if existing:
        store.delete("community_reactions", id=existing[0].get("id"))
        if kind != "POLL":
            counts, poll = _reaction_counts(post_id)
            return {"ok": True, "removed": True, "reactions": counts, "pollCounts": poll}, ""
    store.insert("community_reactions", {
        "community_id": community.get("id"),
        "post_id": post_id,
        "student_id": sid,
        "kind": kind,
        "extra": extra,
        "created_at": _iso(),
    })
    counts, poll = _reaction_counts(post_id)
    return {"ok": True, "reactions": counts, "pollCounts": poll}, ""


def create_event(session, community_id, payload):
    if session.get("user_role") != "student" and not _is_admin(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not community:
        return None, "NOT_FOUND"
    if str(community.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE"
    if not _can_moderate(session, community) and not _is_admin(session):
        return None, "FORBIDDEN"
    if not _rate(session, "event"):
        return None, "RATE_LIMITED"
    title = P.clean_text(payload.get("title") or "", 120)
    if not title:
        return None, "INVALID_EVENT"
    saved = store.insert("community_events", {
        "community_id": community.get("id"),
        "title": title,
        "description": P.clean_text(payload.get("description") or "", 800),
        "start_at": payload.get("startAt") or payload.get("start_at") or "",
        "end_at": payload.get("endAt") or payload.get("end_at") or "",
        "location": P.clean_text(payload.get("location") or "", 160),
        "capacity": _int(payload.get("capacity") or payload.get("maxParticipants"), 0) or 0,
        "registration_deadline": payload.get("registrationDeadline") or payload.get("registration_deadline") or "",
        "created_by": student_id(session) or 0,
        "status": "ACTIVE",
        "created_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    _notify_members(community, "EVENTS", f"Event: {title}", (payload.get("description") or title)[:160])
    return _public_event(saved[0], session), ""


def _event_regs(event_id):
    return [row for row in (store.select("community_event_regs") or []) if str(row.get("event_id")) == str(event_id) and str(row.get("status") or "ACTIVE") == "ACTIVE"]


def _public_event(row, session):
    regs = _event_regs(row.get("id"))
    sid = student_id(session)
    return {
        "id": row.get("id"),
        "communityId": row.get("community_id"),
        "title": row.get("title"),
        "description": row.get("description"),
        "startAt": row.get("start_at"),
        "endAt": row.get("end_at"),
        "location": row.get("location"),
        "capacity": row.get("capacity") or 0,
        "registrationDeadline": row.get("registration_deadline"),
        "registeredCount": len(regs),
        "registered": any(_int(item.get("student_id")) == sid for item in regs),
        "status": row.get("status"),
    }


def list_events(session, community_id):
    if not _can_view(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not _public_community(community, session):
        return None, "NOT_FOUND"
    rows = [row for row in (store.select("community_events") or []) if str(row.get("community_id")) == str(community.get("id")) and str(row.get("status") or "ACTIVE") == "ACTIVE"]
    rows.sort(key=lambda item: str(item.get("start_at") or ""), reverse=True)
    return {"events": [_public_event(row, session) for row in rows]}, ""


def register_event(session, community_id, event_id, cancel=False):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not community or str(community.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE" if community else "NOT_FOUND"
    if not _can_post(session, community):
        return None, "FORBIDDEN"
    event = next((row for row in (store.select("community_events") or []) if str(row.get("id")) == str(event_id)), None)
    if not event or str(event.get("community_id")) != str(community.get("id")):
        return None, "NOT_FOUND"
    sid = student_id(session)
    existing = next((row for row in (store.select("community_event_regs") or []) if str(row.get("event_id")) == str(event_id) and _int(row.get("student_id")) == sid), None)
    if cancel:
        if existing:
            store.update("community_event_regs", {"id": existing.get("id")}, {"status": "CANCELLED"})
        return {"ok": True, "registered": False}, ""
    regs = _event_regs(event_id)
    cap = _int(event.get("capacity"), 0) or 0
    if cap and len(regs) >= cap and not (existing and str(existing.get("status")) == "ACTIVE"):
        return None, "EVENT_FULL"
    if existing:
        store.update("community_event_regs", {"id": existing.get("id")}, {"status": "ACTIVE"})
    else:
        store.insert("community_event_regs", {
            "event_id": event_id,
            "community_id": community.get("id"),
            "student_id": sid,
            "status": "ACTIVE",
            "created_at": _iso(),
        })
    return {"ok": True, "registered": True}, ""


def add_resource(session, community_id, payload):
    if session.get("user_role") != "student" and not _is_admin(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not community or str(community.get("status")) != "ACTIVE":
        return None, "COMMUNITY_UNAVAILABLE" if community else "NOT_FOUND"
    if not _can_post(session, community):
        return None, "FORBIDDEN"
    title = P.clean_text(payload.get("title") or "", 120)
    url = P.safe_url(payload.get("url") or payload.get("link") or "")
    note = P.clean_text(payload.get("note") or payload.get("description") or "", 600)
    if not title or (not url and not note):
        return None, "INVALID_RESOURCE"
    host = urlparse(url).hostname if url else ""
    saved = store.insert("community_resources", {
        "community_id": community.get("id"),
        "title": title,
        "url": url,
        "note": note,
        "category": P.clean_text(payload.get("category") or "Other", 40),
        "host": host or "",
        "content_hash": hashlib.sha256((url or note).encode()).hexdigest() if (url or note) else "",
        "created_by": student_id(session) or 0,
        "status": "ACTIVE",
        "created_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    return _public_resource(saved[0]), ""


def _public_resource(row):
    return {
        "id": row.get("id"),
        "title": row.get("title"),
        "url": row.get("url"),
        "note": row.get("note"),
        "category": row.get("category"),
        "createdAt": row.get("created_at"),
    }


def list_resources(session, community_id):
    if not _can_view(session):
        return None, "FORBIDDEN"
    community = _community(community_id)
    if not _public_community(community, session):
        return None, "NOT_FOUND"
    rows = [row for row in (store.select("community_resources") or []) if str(row.get("community_id")) == str(community.get("id")) and str(row.get("status") or "ACTIVE") == "ACTIVE"]
    return {"resources": [_public_resource(row) for row in rows]}, ""


def create_report(session, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    if not _rate(session, "report"):
        return None, "RATE_LIMITED"
    community = _community(payload.get("communityId") or payload.get("community_id"))
    if not community:
        return None, "NOT_FOUND"
    reason = str(payload.get("reason") or "").strip()
    if reason not in P.REPORT_REASONS:
        return None, "INVALID_REASON"
    target = str(payload.get("targetType") or payload.get("target_type") or "POST").upper()
    if target not in P.REPORT_TARGETS:
        return None, "INVALID_TARGET"
    saved = store.insert("community_reports", {
        "community_id": community.get("id"),
        "reporter_student_id": student_id(session),
        "target_type": target,
        "post_id": payload.get("postId") or payload.get("post_id"),
        "comment_id": payload.get("commentId") or payload.get("comment_id"),
        "resource_id": payload.get("resourceId") or payload.get("resource_id"),
        "reported_student_id": payload.get("reportedStudentId") or payload.get("reported_student_id"),
        "reason": reason,
        "description": P.clean_text(payload.get("description") or "", 400),
        "status": "OPEN",
        "created_at": _iso(),
    })
    if not saved:
        return None, "SAVE_FAILED"
    return {"ok": True, "id": saved[0].get("id")}, ""


def list_reports(session, community_id=None):
    community = _community(community_id) if community_id else None
    if community_id and not community:
        return None, "NOT_FOUND"
    if not _is_admin(session) and not (community and _can_moderate(session, community)):
        return None, "FORBIDDEN"
    rows = store.select("community_reports") or []
    if community:
        rows = [row for row in rows if str(row.get("community_id")) == str(community.get("id"))]
    out = []
    for row in rows:
        out.append({
            "id": row.get("id"),
            "communityId": row.get("community_id"),
            "targetType": row.get("target_type"),
            "postId": row.get("post_id"),
            "commentId": row.get("comment_id"),
            "reason": row.get("reason"),
            "description": row.get("description"),
            "status": row.get("status"),
            "reporterStudentId": row.get("reporter_student_id") if _is_admin(session) else None,
            "createdAt": row.get("created_at"),
            "resolution": row.get("resolution") or "",
        })
    return out, ""


def resolve_report(session, report_id, payload):
    row = next((item for item in (store.select("community_reports") or []) if str(item.get("id")) == str(report_id)), None)
    if not row:
        return None, "NOT_FOUND"
    community = _community(row.get("community_id"))
    if not _is_admin(session) and not (community and _can_moderate(session, community)):
        return None, "FORBIDDEN"
    action = str(payload.get("action") or "NO_ACTION").strip().upper()
    if action not in P.MOD_ACTIONS:
        action = "NO_ACTION"
    reason = P.clean_text(payload.get("reason") or "", 400)
    if action == "CONTENT_REMOVED":
        if row.get("post_id"):
            store.update("community_posts", {"id": row.get("post_id")}, {"status": "REMOVED", "updated_at": _iso()})
        if row.get("comment_id"):
            store.update("community_comments", {"id": row.get("comment_id")}, {"status": "REMOVED"})
        if row.get("resource_id"):
            store.update("community_resources", {"id": row.get("resource_id")}, {"status": "REMOVED"})
    if action == "MEMBER_SUSPENDED" and row.get("reported_student_id") and community:
        member = _membership(community.get("id"), _int(row.get("reported_student_id")))
        if member:
            store.update("community_members", {"id": member.get("id")}, {"status": "SUSPENDED"})
    if action == "COMMUNITY_SUSPENDED" and community and _is_admin(session):
        store.update("communities", {"id": community.get("id")}, {"status": "SUSPENDED", "updated_at": _iso()})
    store.update("community_reports", {"id": row.get("id")}, {
        "status": "ACTIONED" if action != "NO_ACTION" else "DISMISSED",
        "resolution": action,
        "reviewed_by": actor_name(session),
        "reviewed_at": _iso(),
    })
    store.insert("community_moderation", {
        "action": action,
        "actor": actor_name(session),
        "community_id": row.get("community_id"),
        "target_type": row.get("target_type"),
        "target_id": report_id,
        "reason": reason,
        "created_at": _iso(),
    })
    audit(session, "community_report_resolved", "community_reports", report_id, action)
    return {"ok": True, "action": action}, ""


def set_community_status(session, community_id, status, reason=""):
    if not _is_admin(session):
        return None, "FORBIDDEN"
    row = _community(community_id)
    if not row:
        return None, "NOT_FOUND"
    status = str(status or "").upper()
    if status not in P.COMMUNITY_STATUSES:
        return None, "INVALID_STATUS"
    store.update("communities", {"id": row.get("id")}, {"status": status, "updated_at": _iso()})
    store.insert("community_moderation", {
        "action": f"COMMUNITY_{status}",
        "actor": actor_name(session),
        "community_id": row.get("id"),
        "target_type": "COMMUNITY",
        "target_id": row.get("id"),
        "reason": P.clean_text(reason, 400),
        "created_at": _iso(),
    })
    audit(session, "community_status", "communities", row.get("id"), status)
    return {"ok": True, "status": status}, ""


def set_member_role(session, community_id, target_sid, role):
    community = _community(community_id)
    if not community:
        return None, "NOT_FOUND"
    if not _is_admin(session):
        mine = _membership(community.get("id"), student_id(session))
        if not mine or mine.get("role") != "COMMUNITY_ADMIN":
            return None, "FORBIDDEN"
    role = P.normalize_role(role)
    member = _membership(community.get("id"), _int(target_sid))
    if not member or str(member.get("status")) != "ACTIVE":
        return None, "NOT_FOUND"
    store.update("community_members", {"id": member.get("id")}, {"role": role})
    audit(session, "community_role", "community_members", member.get("id"), role)
    return {"ok": True, "role": role}, ""


def remove_post(session, community_id, post_id, reason=""):
    community = _community(community_id)
    if not community or not _can_moderate(session, community):
        return None, "FORBIDDEN"
    post = next((row for row in (store.select("community_posts") or []) if str(row.get("id")) == str(post_id) and str(row.get("community_id")) == str(community.get("id"))), None)
    if not post:
        return None, "NOT_FOUND"
    store.update("community_posts", {"id": post.get("id")}, {"status": "REMOVED", "updated_at": _iso()})
    store.insert("community_moderation", {
        "action": "CONTENT_REMOVED",
        "actor": actor_name(session),
        "community_id": community.get("id"),
        "target_type": "POST",
        "target_id": post_id,
        "reason": P.clean_text(reason, 400),
        "created_at": _iso(),
    })
    return {"ok": True}, ""


def block_student(session, target_sid):
    sid = student_id(session)
    other = _int(target_sid)
    if sid is None or other is None or sid == other:
        return None, "FORBIDDEN"
    existing = [
        row for row in (store.select("community_blocks") or [])
        if _int(row.get("student_id")) == sid and _int(row.get("blocked_student_id")) == other
    ]
    if existing:
        return {"ok": True}, ""
    store.insert("community_blocks", {"student_id": sid, "blocked_student_id": other, "created_at": _iso()})
    return {"ok": True}, ""


def feed(session, offset=0, limit=20):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    sid = student_id(session)
    joined = [
        row.get("community_id")
        for row in (store.select("community_members") or [])
        if _int(row.get("student_id")) == sid and str(row.get("status")) == "ACTIVE"
    ]
    posts = []
    for post in store.select("community_posts") or []:
        if post.get("community_id") not in joined and str(post.get("community_id")) not in {str(j) for j in joined}:
            continue
        community = _community(post.get("community_id"))
        if not community or str(community.get("status")) not in P.VISIBLE_STATUSES | {"SUSPENDED"}:
            continue
        pub = _public_post(post, session, community)
        if pub:
            pub["communityName"] = community.get("name")
            posts.append(pub)
    posts.sort(key=lambda item: str(item.get("createdAt") or ""), reverse=True)
    offset = max(0, _int(offset, 0) or 0)
    limit = max(1, min(50, _int(limit, 20) or 20))
    return {"posts": posts[offset:offset + limit], "total": len(posts)}, ""


def recommend(session):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    sid = student_id(session)
    privacy = _privacy_row(sid) if sid else P.PRIVACY_DEFAULTS
    interests = {str(item).lower() for item in (privacy.get("interests") or [])}
    joined_ids = set()
    joined_cats = set()
    if sid:
        for member in store.select("community_members") or []:
            if _int(member.get("student_id")) == sid and str(member.get("status")) == "ACTIVE":
                joined_ids.add(str(member.get("community_id")))
                comm = _community(member.get("community_id"))
                if comm:
                    joined_cats.add(str(comm.get("category_code") or ""))
    scored = []
    for row in _communities():
        pub = _public_community(row, session)
        if not pub or pub["status"] not in P.VISIBLE_STATUSES or str(pub["id"]) in joined_ids:
            continue
        score = 0
        blob = " ".join([pub["name"], " ".join(pub["tags"]), pub["category"]]).lower()
        if any(item and item in blob for item in interests):
            score += 3
        if pub["categoryCode"] in joined_cats:
            score += 1
        scored.append((score, pub))
    scored.sort(key=lambda item: (-item[0], -item[1]["memberCount"]))
    return {"communities": [item[1] for item in scored[:8]]}, ""


def analytics(session, community_id=None):
    if community_id:
        community = _community(community_id)
        if not community or not _can_moderate(session, community):
            return None, "FORBIDDEN"
        posts = [row for row in (store.select("community_posts") or []) if str(row.get("community_id")) == str(community.get("id")) and str(row.get("status")) == "ACTIVE"]
        reports = [row for row in (store.select("community_reports") or []) if str(row.get("community_id")) == str(community.get("id"))]
        return {
            "memberCount": _member_count(community.get("id")),
            "postCount": len(posts),
            "eventCount": len([row for row in (store.select("community_events") or []) if str(row.get("community_id")) == str(community.get("id"))]),
            "openReports": len([row for row in reports if str(row.get("status")) == "OPEN"]),
        }, ""
    if not _is_admin(session):
        return None, "FORBIDDEN"
    return {
        "communityCount": len([row for row in _communities() if str(row.get("status")) == "ACTIVE"]),
        "pendingRequests": len([row for row in (store.select("community_requests") or []) if str(row.get("status")) == "PENDING"]),
        "openReports": len([row for row in (store.select("community_reports") or []) if str(row.get("status")) == "OPEN"]),
    }, ""


def overview(session):
    if not _can_view(session):
        return None, "FORBIDDEN"
    ensure_seed()
    listed, _ = list_communities(session, {"limit": 8})
    mine, _ = list_communities(session, {"mine": True, "limit": 8}) if session.get("user_role") == "student" else ({"communities": []}, "")
    rec, _ = recommend(session)
    cats, _ = list_categories(session)
    pending = []
    if session.get("user_role") == "student":
        pending = [row for row in (list_requests(session)[0] or []) if row.get("status") in {"PENDING", "CHANGES_REQUESTED"}]
    return {
        "categories": cats or [],
        "recommended": (rec or {}).get("communities") or [],
        "mine": (mine or {}).get("communities") or [],
        "popular": (listed or {}).get("communities") or [],
        "myRequests": pending,
        "disclaimer": "Student ID is the default identity. Names appear only when a student chooses to share them.",
    }, ""


def student_summary(session):
    sid = student_id(session)
    if sid is None:
        return {"available": False}
    ensure_seed()
    mine = [
        row for row in (store.select("community_members") or [])
        if _int(row.get("student_id")) == sid and str(row.get("status")) == "ACTIVE"
    ]
    return {"available": True, "joinedCount": len(mine)}
