"""Community rules: uniqueness, privacy defaults, roles, content limits."""

from __future__ import annotations

import re

INSTITUTION_ID = "default"

DEFAULT_CATEGORIES = (
    ("SPORTS", "Sports", 10),
    ("ACTIVITIES", "Activities", 20),
    ("TECHNICAL", "Technical", 30),
    ("ACADEMIC", "Academic", 40),
    ("CULTURAL", "Cultural", 50),
    ("FESTIVE", "Festive", 60),
    ("ARTS", "Arts", 70),
    ("MUSIC", "Music", 80),
    ("CAREER", "Career", 90),
    ("HOBBIES", "Hobbies", 100),
    ("OTHER", "Other", 110),
)

REQUEST_STATUSES = ("PENDING", "CHANGES_REQUESTED", "APPROVED", "REJECTED")
COMMUNITY_STATUSES = ("ACTIVE", "SUSPENDED", "ARCHIVED")
VISIBLE_STATUSES = frozenset({"ACTIVE"})
MEMBER_ROLES = ("MEMBER", "MODERATOR", "COMMUNITY_ADMIN")
MEMBER_STATUSES = ("ACTIVE", "LEFT", "SUSPENDED")
POST_KINDS = ("POST", "ANNOUNCEMENT", "POLL")
POST_STATUSES = ("ACTIVE", "REMOVED", "HIDDEN")
REACTIONS = ("LIKE", "INTERESTED", "HELPFUL")
REPORT_REASONS = (
    "Spam",
    "Harassment",
    "Abuse",
    "Inappropriate content",
    "Misleading content",
    "Academic misconduct",
    "Illegal content",
    "Privacy violation",
    "Other",
)
REPORT_TARGETS = ("COMMUNITY", "POST", "COMMENT", "MEMBER", "RESOURCE", "EVENT")
MOD_ACTIONS = (
    "NO_ACTION",
    "WARNING",
    "CONTENT_REMOVED",
    "MEMBER_SUSPENDED",
    "COMMUNITY_SUSPENDED",
    "COMMUNITY_ARCHIVED",
    "REQUEST_APPROVED",
    "REQUEST_REJECTED",
    "REQUEST_CHANGES",
    "MODERATOR_ADDED",
    "MODERATOR_REMOVED",
)
NOTIFY_PREFS = ("ALL", "ANNOUNCEMENTS", "EVENTS", "NONE")
RESOURCE_CATEGORIES = (
    "Learning Material",
    "Practice",
    "Reference",
    "Event Material",
    "Competition",
    "Tutorial",
    "Other",
)

PRIVACY_DEFAULTS = {
    "show_name": False,
    "show_photo": False,
    "show_department": False,
    "show_semester": False,
    "show_skills": False,
    "show_bio": False,
    "show_portfolio": False,
}

DEFAULT_RULES = (
    "Be respectful.\n"
    "No harassment, bullying, or doxxing.\n"
    "No spam or unauthorized personal information.\n"
    "No exam leaks, cheating, or academic misconduct.\n"
    "No malicious links.\n"
    "Connect first; reveal identity only if you choose to."
)

DEFAULT_SETTINGS = {
    "enabled": True,
    "max_memberships": 50,
    "max_name": 80,
    "max_description": 800,
    "max_post": 2000,
    "max_comment": 800,
    "max_bio": 280,
    "near_duplicate": 0.92,
    "potential_duplicate": 0.55,
}

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_RESOURCE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".pdf", ".txt"}

TAG_RE = re.compile(r"<[^>]+>")
SCRIPT_RE = re.compile(r"(?is)<script.*?>.*?</script>|javascript:|data:text/html")


def normalize_settings(raw=None):
    cfg = dict(DEFAULT_SETTINGS)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in cfg or value is None:
                continue
            if isinstance(cfg[key], bool):
                cfg[key] = bool(value)
            elif isinstance(cfg[key], int):
                try:
                    cfg[key] = max(1, int(value))
                except (TypeError, ValueError):
                    continue
            elif isinstance(cfg[key], float):
                try:
                    cfg[key] = float(value)
                except (TypeError, ValueError):
                    continue
    return cfg


def clean_text(value, limit=2000):
    text = SCRIPT_RE.sub("", str(value or ""))
    text = TAG_RE.sub("", text)
    text = text.replace("\x00", " ").strip()
    return text[: int(limit)]


def safe_url(value):
    url = str(value or "").strip()
    if not url:
        return ""
    low = url.lower()
    if low.startswith("javascript:") or low.startswith("data:"):
        return ""
    if not (low.startswith("http://") or low.startswith("https://")):
        return ""
    return url[:500]


def slugify(name):
    text = re.sub(r"[^a-z0-9]+", "-", str(name or "").lower()).strip("-")
    return (text or "community")[:80]


def normalize_pref(value):
    text = str(value or "ALL").strip().upper()
    return text if text in NOTIFY_PREFS else "ALL"


def normalize_reaction(value):
    text = str(value or "").strip().upper()
    return text if text in REACTIONS else ""


def normalize_role(value):
    text = str(value or "MEMBER").strip().upper()
    return text if text in MEMBER_ROLES else "MEMBER"
