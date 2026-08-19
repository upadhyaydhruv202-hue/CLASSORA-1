"""In-app notifications. Never include hidden mentorship identities."""

from src.success import store


def notify(*, role, recipient_id, title, body):
    if not title:
        return None
    return store.insert("notifications", {
        "recipient_role": role,
        "recipient_id": str(recipient_id) if recipient_id is not None else None,
        "title": title[:160],
        "body": (body or "")[:500],
    })


def for_recipient(*, role, recipient_id, limit=30):
    rows = store.select("notifications") or []
    rid = str(recipient_id) if recipient_id is not None else None
    out = []
    for r in rows:
        if r.get("recipient_role") and r.get("recipient_role") != role:
            continue
        if rid and r.get("recipient_id") not in (None, "", rid):
            continue
        out.append(r)
    out.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return out[:limit]


def maybe_notify_risk(profile, previous_row):
    """Alert when category worsens. Body uses category, not another person's name for students."""
    pred = (profile or {}).get("prediction") or {}
    category = pred.get("category")
    if category not in ("High", "Critical"):
        return
    prev_cat = (previous_row or {}).get("category")
    if prev_cat == category:
        return
    sid = profile.get("student_id")
    notify(
        role="student",
        recipient_id=sid,
        title="Your support picture changed",
        body="A new support estimate is available on My Progress. This is not a diagnosis.",
    )
    notify(
        role="counsellor",
        recipient_id="caseload",
        title=f"Predicted {category} support-risk",
        body=f"Student ID {sid} moved to {category}. Open Digital Twin / Student 360.",
    )
    notify(
        role="administrator",
        recipient_id="ops",
        title=f"Risk category {category}",
        body="A monitored student crossed a support threshold. Aggregates are on Ecosystem analytics.",
    )
