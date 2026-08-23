"""Configurable reward policy engine. Points are never calculated in the UI."""

from __future__ import annotations

from datetime import datetime, timezone

INSTITUTION_ID = "default"
ANALYSIS_VERSION = "rewards-v1.0"
EDUCATION_LEVELS = ("PRIMARY", "SECONDARY", "HIGHER_SECONDARY", "UNDERGRADUATE", "POSTGRADUATE")

CATEGORIES = (
    "ACADEMIC", "ACADEMIC_IMPROVEMENT", "SPORTS", "HACKATHON", "COMPETITION",
    "CERTIFICATION", "INTERNSHIP", "RESEARCH", "PROJECT", "INNOVATION",
    "NSS", "NCC", "BOOTCAMP", "WORKSHOP", "SEMINAR", "CONFERENCE",
    "LEADERSHIP", "VOLUNTEERING", "CULTURAL", "CLUB_ACTIVITY",
    "COMMUNITY_SERVICE", "ATTENDANCE", "MENTORSHIP", "OTHER",
)

LEVELS = (
    "PARTICIPATION", "INSTITUTIONAL", "INTER_COLLEGE", "INTER_UNIVERSITY",
    "DISTRICT", "STATE", "NATIONAL", "INTERNATIONAL",
)

POSITIONS = (
    "NONE", "PARTICIPATION", "FINALIST", "TOP_10", "POSITION_3", "POSITION_2",
    "POSITION_1", "RUNNER_UP", "WINNER", "BEST_INNOVATION", "JURY_AWARD",
)

TX_EARN = "EARN"
TX_REDEEM = "REDEEM"
TX_EXPIRE = "EXPIRE"
TX_ADJUSTMENT = "ADJUSTMENT"
TX_REVERSAL = "REVERSAL"
TX_REFUND = "REFUND"
TX_BONUS = "BONUS"
TX_PENALTY = "PENALTY"
TX_TYPES = (TX_EARN, TX_REDEEM, TX_EXPIRE, TX_ADJUSTMENT, TX_REVERSAL, TX_REFUND, TX_BONUS, TX_PENALTY)

# Posted ledger signs. ADJUSTMENT uses the stored integer sign.
TX_SIGN = {
    TX_EARN: 1, TX_BONUS: 1, TX_REFUND: 1,
    TX_REDEEM: -1, TX_EXPIRE: -1, TX_REVERSAL: -1, TX_PENALTY: -1,
}

ACH_PENDING = "PENDING_VERIFICATION"
ACH_APPROVAL = "PENDING_APPROVAL"
ACH_APPROVED = "APPROVED"
ACH_REJECTED = "REJECTED"
ACH_CHANGES = "CHANGES_REQUESTED"
ACH_STATUSES = (ACH_PENDING, ACH_APPROVAL, ACH_APPROVED, ACH_REJECTED, ACH_CHANGES)

VOUCHER_ACTIVE = "ACTIVE"
VOUCHER_REDEEMED = "REDEEMED"
VOUCHER_EXPIRED = "EXPIRED"
VOUCHER_CANCELLED = "CANCELLED"
VOUCHER_REFUNDED = "REFUNDED"
VOUCHER_SUSPENDED = "SUSPENDED"

MERCHANT_CATEGORIES = ("FOOD", "CANTEEN", "STATIONERY", "XEROX", "PRINTING", "BOOKS", "MERCHANDISE", "OTHER")
DISCOUNT_TYPES = ("PERCENTAGE", "FIXED_AMOUNT", "FREE_ITEM", "BOGO", "POINTS_ONLY", "HYBRID")

MILESTONES = (100, 250, 500, 1000)
BADGE_MAP = {
    "ACADEMIC": ("Academic Achiever", "Academic"),
    "ACADEMIC_IMPROVEMENT": ("Consistent Performer", "Improvement"),
    "SPORTS": ("Sports Champion", "Sports"),
    "HACKATHON": ("Hackathon Hero", "Innovation"),
    "INNOVATION": ("Innovation Explorer", "Innovation"),
    "RESEARCH": ("Research Explorer", "Research"),
    "LEADERSHIP": ("Leadership Star", "Leadership"),
    "NSS": ("Community Contributor", "Community"),
    "NCC": ("Community Contributor", "Community"),
    "VOLUNTEERING": ("Community Contributor", "Community"),
    "COMMUNITY_SERVICE": ("Campus Contributor", "Community"),
    "INTERNSHIP": ("Campus Contributor", "Career"),
}

# Default configuration only. Not used as a live hardcoded award path once policies are stored.
DEFAULT_POLICIES = (
    ("ACADEMIC_IMPROVEMENT", "IMPROVEMENT", "INSTITUTIONAL", 100, False),
    ("ATTENDANCE", "IMPROVEMENT", "INSTITUTIONAL", 75, False),
    ("HACKATHON", "PARTICIPATION", "INSTITUTIONAL", 100, False),
    ("HACKATHON", "FINALIST", "INSTITUTIONAL", 200, True),
    ("HACKATHON", "WINNER", "INSTITUTIONAL", 500, True),
    ("SPORTS", "PARTICIPATION", "INTER_COLLEGE", 100, False),
    ("SPORTS", "PARTICIPATION", "INTER_UNIVERSITY", 150, True),
    ("SPORTS", "PARTICIPATION", "STATE", 250, True),
    ("SPORTS", "PARTICIPATION", "NATIONAL", 400, True),
    ("SPORTS", "PARTICIPATION", "INTERNATIONAL", 750, True),
    ("SPORTS", "WINNER", "INTER_COLLEGE", 200, True),
    ("NSS", "PARTICIPATION", "INSTITUTIONAL", 75, False),
    ("NCC", "PARTICIPATION", "INSTITUTIONAL", 75, False),
    ("INTERNSHIP", "COMPLETION", "INSTITUTIONAL", 200, True),
    ("CERTIFICATION", "COMPLETION", "INSTITUTIONAL", 100, True),
    ("PROJECT", "COMPLETED", "INSTITUTIONAL", 100, False),
    ("LEADERSHIP", "PARTICIPATION", "INSTITUTIONAL", 100, True),
    ("MENTORSHIP", "RECOGNITION", "INSTITUTIONAL", 50, False),
    ("VOLUNTEERING", "PARTICIPATION", "INSTITUTIONAL", 75, False),
    ("RESEARCH", "PUBLICATION", "NATIONAL", 400, True),
)

DEFAULT_SETTINGS = {
    "rewards_enabled": True,
    "merchant_redemption_enabled": True,
    "achievement_submission_enabled": True,
    "leaderboard_enabled": False,
    "automatic_rewards_enabled": True,
    "education_level": "UNDERGRADUATE",
    "institution_id": INSTITUTION_ID,
    "point_expiry_days": 180,
    "voucher_expiry_days": 15,
    "direct_award_max": 100,
    "high_approval_threshold": 500,
    "daily_student_cap": 1000,
    "weekly_student_cap": 2500,
    "monthly_student_cap": 5000,
    "daily_issuer_cap": 800,
    "self_approval": False,
    "policy_priority": "HIGHEST",
    "notify_expiry_days": [7, 3, 1],
    "expiring_soon_days": 7,
    "timezone": "Asia/Kolkata",
    "allow_manual_point_override": False,
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
            if key == "notify_expiry_days" and isinstance(value, list):
                cfg[key] = [int(v) for v in value if str(v).isdigit() or isinstance(v, int)]
                continue
            try:
                if isinstance(cfg[key], bool):
                    cfg[key] = bool(value) if not isinstance(value, str) else value.lower() in ("1", "true", "yes")
                elif isinstance(cfg[key], int):
                    cfg[key] = int(value)
                else:
                    cfg[key] = type(cfg[key])(value)
            except (TypeError, ValueError):
                continue
    if cfg["education_level"] not in EDUCATION_LEVELS:
        cfg["education_level"] = "UNDERGRADUATE"
    cfg["direct_award_max"] = max(0, int(cfg["direct_award_max"]))
    cfg["point_expiry_days"] = max(1, int(cfg["point_expiry_days"]))
    cfg["voucher_expiry_days"] = max(1, int(cfg["voucher_expiry_days"]))
    return cfg


def signed_points(txn_type, points):
    amount = int(points or 0)
    if txn_type == TX_ADJUSTMENT:
        return amount
    sign = TX_SIGN.get(txn_type, 0)
    return sign * abs(amount)


def match_policies(policies, category, achievement_type, achievement_level, at=None):
    stamp = at or datetime.now(timezone.utc)
    rows = []
    for row in policies or []:
        if not row.get("active", True):
            continue
        if str(row.get("category") or "") != str(category or ""):
            continue
        start = parse_ts(row.get("valid_from"))
        end = parse_ts(row.get("valid_until"))
        if start and stamp < start:
            continue
        if end and stamp > end:
            continue
        type_ok = not row.get("achievement_type") or str(row.get("achievement_type")) in (str(achievement_type or ""), "*")
        level_ok = not row.get("achievement_level") or str(row.get("achievement_level")) in (str(achievement_level or ""), "*")
        if type_ok and level_ok:
            rows.append(row)
    return rows


def recommend_points(policies, category, achievement_type, achievement_level, priority="HIGHEST"):
    rows = match_policies(policies, category, achievement_type, achievement_level)
    if not rows:
        return None
    if str(priority or "HIGHEST").upper() == "ADDITIVE":
        total = sum(int(row.get("points") or 0) for row in rows)
        approval = any(row.get("approval_required") for row in rows)
        return {"points": total, "approvalRequired": approval, "policyIds": [row.get("id") for row in rows], "mode": "ADDITIVE"}
    best = max(rows, key=lambda row: int(row.get("points") or 0))
    return {
        "points": int(best.get("points") or 0),
        "approvalRequired": bool(best.get("approval_required")),
        "policyIds": [best.get("id")],
        "mode": "HIGHEST",
        "policy": best,
    }


def duplicate_key(student_id, category, achievement_type, event_key, occurred_at, certificate_id=""):
    day = str(occurred_at or "")[:10]
    token = str(certificate_id or event_key or "").strip().lower()
    return f"{student_id}|{category}|{achievement_type}|{token}|{day}"


def category_label(code):
    return str(code or "").replace("_", " ").title()
