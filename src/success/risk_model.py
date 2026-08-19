"""Isolated Student Success risk model. Does not import face/voice pipelines."""

from collections import defaultdict
from datetime import datetime, timedelta

MODEL_VERSION = "success-risk-v1.1"
CAUSALITY_DISCLAIMER = (
    "These are associated support signals and estimated contributions, "
    "not proven causes, diagnoses, or guaranteed dropout outcomes. "
    "A human reviewer must approve any intervention."
)

DEFAULT_LIBRARY = [
    {"name": "Attendance check-in", "domain": "attendance", "owner_role": "counsellor", "available": True, "success_criteria": "Attendance rate improves over 2 weeks"},
    {"name": "Academic tutoring referral", "domain": "academic", "owner_role": "faculty", "available": True, "success_criteria": "Assessment scores stabilize"},
    {"name": "Mentor weekly meeting", "domain": "mentoring", "owner_role": "mentor", "available": True, "success_criteria": "Student attends 2 mentor sessions"},
    {"name": "Study-skills workshop", "domain": "academic", "owner_role": "faculty", "available": True, "success_criteria": "Assignment completion improves"},
    {"name": "Engagement nudge", "domain": "engagement", "owner_role": "counsellor", "available": True, "success_criteria": "LMS activity resumes"},
    {"name": "Financial-support referral", "domain": "financial", "owner_role": "counsellor", "available": False, "success_criteria": "Support application started"},
]


def _parse_ts(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def attendance_features(logs):
    logs = sorted(logs or [], key=lambda r: str(r.get("timestamp") or ""))
    total = len(logs)
    present = sum(1 for r in logs if r.get("is_present"))
    rate = round(100.0 * present / total, 1) if total else None
    consec = 0
    streak = 0
    for r in reversed(logs):
        if r.get("is_present"):
            break
        streak += 1
        consec = streak
    recent = logs[-6:] if logs else []
    older = logs[-12:-6] if len(logs) >= 12 else []
    recent_rate = (sum(1 for r in recent if r.get("is_present")) / len(recent) * 100) if recent else None
    older_rate = (sum(1 for r in older if r.get("is_present")) / len(older) * 100) if older else None
    decline = None
    if recent_rate is not None and older_rate is not None:
        decline = round(older_rate - recent_rate, 1)
    return {
        "marked": total,
        "present": present,
        "absent": total - present,
        "rate": rate,
        "consecutive_absences": consec,
        "sudden_decline": decline,
        "chronic": bool(rate is not None and rate < 50 and total >= 6),
    }


def academic_features(records):
    records = records or []
    if not records:
        return {"gpa": None, "failed": 0, "backlogs": 0, "avg_score": None, "count": 0, "completion": None}
    scores = []
    failed = 0
    backlogs = 0
    gpas = []
    for r in records:
        if r.get("gpa") is not None:
            gpas.append(float(r["gpa"]))
        if r.get("score") is not None and r.get("max_score"):
            pct = 100.0 * float(r["score"]) / float(r["max_score"])
            scores.append(pct)
            if pct < 40:
                failed += 1
        if r.get("backlog"):
            backlogs += 1
    scored = len(scores)
    return {
        "gpa": round(sum(gpas) / len(gpas), 2) if gpas else None,
        "failed": failed,
        "backlogs": backlogs,
        "avg_score": round(sum(scores) / len(scores), 1) if scores else None,
        "count": len(records),
        "completion": round(100.0 * scored / len(records), 1) if records else None,
    }


def engagement_features(events):
    events = events or []
    if not events:
        return {"count": 0, "inactive_days": None, "trend": None}
    times = [_parse_ts(e.get("occurred_at") or e.get("timestamp")) for e in events]
    times = [t for t in times if t]
    last = max(times) if times else None
    inactive = (datetime.now() - last).days if last else None
    return {"count": len(events), "inactive_days": inactive, "trend": "low" if (inactive or 0) > 14 else "ok"}


def score_student(att, aca, eng, thresholds=None, support=None):
    """Deterministic isolated risk score. Missing signals lower confidence.

    ``support`` may include mentorship_active. That is an associated support
    adjustment, not a guaranteed causal effect.
    """
    t = thresholds or {"critical": 70, "high": 50, "watch": 30}
    contrib = []
    missing = []
    score = 0.0

    if att["rate"] is None:
        missing.append("attendance")
    else:
        att_risk = max(0, 100 - att["rate"])
        w = 0.55
        score += w * att_risk
        contrib.append(("Attendance rate", round(w * att_risk, 1), "negative" if att_risk > 25 else "positive"))
        if att["consecutive_absences"] >= 3:
            extra = min(15, att["consecutive_absences"] * 3)
            score += extra
            contrib.append(("Consecutive absences", extra, "negative"))
        if att["sudden_decline"] and att["sudden_decline"] >= 20:
            score += 10
            contrib.append(("Sudden attendance decline", 10, "negative"))
        if att["rate"] >= 80:
            contrib.append(("Stable attendance", -5, "positive"))

    if aca["count"] == 0:
        missing.append("academic")
    else:
        if aca["avg_score"] is not None:
            acad_risk = max(0, 60 - aca["avg_score"]) * 0.4
            score += acad_risk
            contrib.append(("Assessment performance", round(acad_risk, 1), "negative" if acad_risk > 5 else "positive"))
        score += aca["failed"] * 6 + aca["backlogs"] * 4
        if aca["failed"]:
            contrib.append(("Failed assessments", aca["failed"] * 6, "negative"))
        if aca.get("completion") is not None and aca["completion"] < 70:
            extra = round((70 - aca["completion"]) * 0.12, 1)
            score += extra
            contrib.append(("Assignment completion", extra, "negative"))

    if eng["count"] == 0:
        missing.append("engagement")
    else:
        if (eng["inactive_days"] or 0) > 14:
            score += 8
            contrib.append(("LMS inactivity", 8, "negative"))

    if support and support.get("mentorship_active"):
        score = max(0, score - 8)
        contrib.append(("Active mentorship", -8, "positive"))

    score = round(min(100, max(0, score)), 1)
    if score >= t["critical"]:
        category = "Critical"
    elif score >= t["high"]:
        category = "High"
    elif score >= t["watch"]:
        category = "Watch"
    else:
        category = "Stable"

    confidence = round(max(0.35, 1.0 - 0.22 * len(missing)), 2)
    probability = round(score / 100.0, 3)
    payload = {
        "score": score,
        "category": category,
        "probability": probability,
        "confidence": confidence,
        "missing": missing,
        "contributors": contrib,
        "model_version": MODEL_VERSION,
        "disclaimer": CAUSALITY_DISCLAIMER,
    }
    payload["drivers"] = explain_drivers(payload)
    payload["widgetLevel"] = widget_level(score, category)
    return payload


def widget_level(score, category=None, thresholds=None):
    """LOW / MODERATE / HIGH for the live widget, mapped from production thresholds.

    Critical (≥70) → HIGH, Stable (<30) → LOW, Watch/High (30–69) → MODERATE.
    """
    if score is None:
        return None
    t = thresholds or {"critical": 70, "high": 50, "watch": 30}
    try:
        score = float(score)
    except (TypeError, ValueError):
        return None
    if category == "Critical" or score >= t["critical"]:
        return "HIGH"
    if category == "Stable" or score < t["watch"]:
        return "LOW"
    return "MODERATE"


def widget_level_label(level: str | None) -> str:
    return {
        "LOW": "LOW RISK",
        "MODERATE": "MODERATE RISK",
        "HIGH": "HIGH RISK",
    }.get(level or "", "RISK SCORE")


def recommend(prediction, att, library=None):
    library = [x for x in (library or DEFAULT_LIBRARY) if x.get("available")]
    recs = []
    if att.get("rate") is not None and att["rate"] < 75:
        recs.append(next((x for x in library if x["domain"] == "attendance"), None))
    if "academic" not in prediction["missing"] and prediction["score"] >= 40:
        recs.append(next((x for x in library if x["domain"] == "academic"), None))
    recs.append(next((x for x in library if x["domain"] == "mentoring"), None))
    out = []
    seen = set()
    for item in recs:
        if not item or item["name"] in seen:
            continue
        seen.add(item["name"])
        out.append({
            "name": item["name"],
            "reason": f"Associated with {prediction['category']} predicted risk (score {prediction['score']}).",
            "owner": item.get("owner_role"),
            "confidence": prediction["confidence"],
            "channel": "in_app",
            "fallback": "rules/knowledge",
        })
    if not out:
        out.append({
            "name": "Monitor and check-in",
            "reason": "Insufficient history for a specialized package; using transparent rules fallback.",
            "owner": "counsellor",
            "confidence": prediction["confidence"],
            "channel": "in_app",
            "fallback": "rules/knowledge",
        })
    return out


def simulate_what_if(prediction, attendance_delta_pct):
    """Backward-compatible attendance-only estimate. Prefer simulate_changes()."""
    new_score = round(min(100, max(0, prediction["score"] - attendance_delta_pct * 0.55)), 1)
    return {
        "label": "SIMULATED / ESTIMATED",
        "current_score": prediction["score"],
        "estimated_score": new_score,
        "note": "Not a guaranteed outcome. Counterfactual only. Attendance-only shortcut; full recovery uses the live scorer.",
    }


DRIVER_BUCKETS = (
    ("Attendance Decline", ("Attendance rate", "Sudden attendance decline", "Consecutive absences", "Stable attendance")),
    ("Academic Performance", ("Assessment performance", "Failed assessments")),
    ("Engagement Decline", ("LMS inactivity",)),
    ("Assignment Completion", ("Assignment completion",)),
    ("Recent Behavior", ("Consecutive absences", "Sudden attendance decline")),
    ("Mentorship / support", ("Active mentorship",)),
)


def explain_drivers(prediction) -> list[dict]:
    """Exact additive attribution from success-risk-v1.1 (not SHAP — the model is not a black box)."""
    contrib = prediction.get("contributors") or []
    raw = {name: 0.0 for name, _ in DRIVER_BUCKETS}
    assigned = set()
    mapping = {
        "Attendance rate": "Attendance Decline",
        "Sudden attendance decline": "Attendance Decline",
        "Stable attendance": "Attendance Decline",
        "Assessment performance": "Academic Performance",
        "Failed assessments": "Academic Performance",
        "LMS inactivity": "Engagement Decline",
        "Assignment completion": "Assignment Completion",
        "Consecutive absences": "Recent Behavior",
        "Active mentorship": "Mentorship / support",
    }
    other = 0.0
    for factor, value, _direction in contrib:
        bucket = mapping.get(factor)
        mag = float(value)
        if bucket:
            raw[bucket] += max(0.0, mag)
            assigned.add(factor)
        else:
            other += max(0.0, mag)
    raw["Other"] = other
    total = sum(raw.values()) or 1.0
    drivers = []
    for name in [n for n, _ in DRIVER_BUCKETS] + ["Other"]:
        pct = round(100.0 * raw.get(name, 0.0) / total, 1)
        if pct <= 0 and name == "Other":
            continue
        drivers.append({
            "name": name,
            "percent": pct,
            "points": round(raw.get(name, 0.0), 1),
            "bar": "█" * max(0, int(round(pct / 4))) or ("░" if pct == 0 else "█"),
        })
    return drivers


def bar_line(driver: dict) -> str:
    return f"{driver['name']:<24} {driver['bar']:<14} {driver['percent']}%"


def temporal_features(att) -> dict:
    """Distinguish currently low vs rapidly deteriorating (uses existing 6-session windows)."""
    rate = att.get("rate")
    decline = att.get("sudden_decline")
    currently_low = bool(rate is not None and rate < 70)
    rapid = bool(decline is not None and decline >= 15)
    if rapid and currently_low:
        pattern = "rapidly_deteriorating"
        label = "Performance is rapidly deteriorating, not only currently low."
        velocity = round(float(decline) / 14.0, 3)
    elif rapid:
        pattern = "deteriorating"
        label = "Recent attendance is falling quickly."
        velocity = round(float(decline) / 14.0, 3)
    elif currently_low:
        pattern = "currently_low"
        label = "Current performance is low; recent change is not a sharp drop."
        velocity = 0.0
    else:
        pattern = "stable_or_improving"
        label = "No rapid deterioration signal in the available attendance windows."
        velocity = round(float(decline or 0) / 14.0, 3)
    return {
        "pattern": pattern,
        "label": label,
        "velocity": velocity,
        "currently_low": currently_low,
        "rapidly_deteriorating": rapid,
        "sudden_decline_pp": decline,
    }


def narrative_why(att, aca, eng, prediction, *, role="staff") -> dict:
    why = []
    if att.get("sudden_decline") and att["sudden_decline"] >= 10:
        why.append(f"Attendance has fallen by {att['sudden_decline']}% across the last two recorded windows.")
    elif att.get("rate") is not None and att["rate"] < 75:
        why.append(f"Recorded attendance is {att['rate']}%, below the 75% support threshold.")
    if att.get("consecutive_absences", 0) >= 3:
        why.append(f"{att['consecutive_absences']} consecutive absences are on record.")
    if aca.get("completion") is not None and aca["completion"] < 80:
        why.append("Assignment / assessment completion is incomplete in the records we have.")
    if aca.get("avg_score") is not None and aca["avg_score"] < 55:
        why.append("Academic scores show a downward or below-support average.")
    if aca.get("failed"):
        why.append(f"{aca['failed']} assessment(s) are below 40%.")
    if (eng.get("inactive_days") or 0) > 14:
        why.append("Platform / LMS engagement has been inactive for more than 14 days.")
    if not why:
        if prediction.get("missing"):
            why.append("Some layers have no data yet (listed as missing). The estimate uses what is available.")
        else:
            why.append("Available signals do not show a concentrated risk driver.")
    recs = []
    if att.get("rate") is not None and att["rate"] < 80:
        recs.append("Encourage attendance improvement and a short check-in.")
    if aca.get("count"):
        recs.append("Assign targeted academic support for incomplete or low-score work.")
    recs.append("Start or continue anonymous counseling if the student wants support.")
    recs.append("Schedule academic mentoring.")
    if role == "student":
        recs = [
            "Keep attending class — small gains in attendance move this estimate.",
            "Complete pending assignments when they are on your list.",
            "Use anonymous mentorship if you want a private conversation.",
            "Ask a counsellor for a recovery plan if you want structured steps.",
        ]
    return {
        "title": "WHY IS THIS STUDENT AT RISK?" if role != "student" else "WHAT IS AFFECTING YOUR SUPPORT PICTURE?",
        "why": why,
        "recommended": recs,
        "disclaimer": CAUSALITY_DISCLAIMER,
        "method": (
            "Feature contributions are exact additives from the production rules model "
            f"({MODEL_VERSION}). SHAP/LIME are not applied because this is not a trained black-box estimator."
        ),
    }


def _clamp(value, lo, hi):
    if value is None:
        return None
    return max(lo, min(hi, value))


def apply_feature_changes(att, aca, eng, changes: dict, support=None):
    """Copy features and apply practical deltas, then re-run the live scorer."""
    att2 = dict(att or {})
    aca2 = dict(aca or {})
    eng2 = dict(eng or {})
    sup2 = dict(support or {})
    if changes.get("attendance_delta") and att2.get("rate") is not None:
        att2["rate"] = round(_clamp(att2["rate"] + float(changes["attendance_delta"]), 0, 100), 1)
        if changes["attendance_delta"] > 0:
            att2["consecutive_absences"] = 0
            if att2.get("sudden_decline"):
                att2["sudden_decline"] = max(0, att2["sudden_decline"] - float(changes["attendance_delta"]))
    if changes.get("attendance_set") is not None:
        att2["rate"] = round(_clamp(float(changes["attendance_set"]), 0, 100), 1)
    if changes.get("academic_delta") and aca2.get("avg_score") is not None:
        aca2["avg_score"] = round(_clamp(aca2["avg_score"] + float(changes["academic_delta"]), 0, 100), 1)
        aca2["count"] = max(aca2.get("count") or 1, 1)
    if changes.get("completion_delta") and aca2.get("completion") is not None:
        aca2["completion"] = round(_clamp(aca2["completion"] + float(changes["completion_delta"]), 0, 100), 1)
        aca2["count"] = max(aca2.get("count") or 1, 1)
    if changes.get("engagement_resume"):
        eng2["inactive_days"] = 1
        eng2["count"] = max(eng2.get("count") or 1, 1)
        eng2["trend"] = "ok"
    if "mentorship_active" in changes:
        sup2["mentorship_active"] = bool(changes["mentorship_active"])
    return att2, aca2, eng2, sup2


def simulate_changes(att, aca, eng, changes: dict, support=None, current=None):
    att2, aca2, eng2, sup2 = apply_feature_changes(att, aca, eng, changes, support)
    pred = score_student(att2, aca2, eng2, support=sup2)
    current_score = (current or {}).get("score")
    if current_score is None:
        current_score = score_student(att, aca, eng, support=support)["score"]
    return {
        "label": "SIMULATED / ESTIMATED",
        "current_score": current_score,
        "estimated_score": pred["score"],
        "estimated_category": pred["category"],
        "delta": round(current_score - pred["score"], 1),
        "changes": changes,
        "prediction": pred,
        "note": "Re-scored with the live rules model. Not a guaranteed outcome.",
    }


def recovery_scenarios(att, aca, eng, support=None) -> dict:
    """Practical counterfactuals + the cheapest combination that improves category or ≥10 points."""
    current = score_student(att, aca, eng, support=support)
    specs = [
        {"id": "S1", "title": "Attendance +8 pp", "changes": {"attendance_delta": 8}},
        {"id": "S2", "title": "Attendance +13 pp", "changes": {"attendance_delta": 13}},
        {"id": "S3", "title": "Attendance +13 pp and assignments +15 pp", "changes": {"attendance_delta": 13, "completion_delta": 15, "academic_delta": 10}},
        {"id": "S4", "title": "Attendance +13 pp, assignments +20 pp, mentorship active", "changes": {"attendance_delta": 13, "completion_delta": 20, "academic_delta": 15, "mentorship_active": True}},
        {"id": "S5", "title": "Mentorship only", "changes": {"mentorship_active": True}},
        {"id": "S6", "title": "Resume engagement", "changes": {"engagement_resume": True}},
    ]
    usable = []
    for spec in specs:
        skip = False
        ch = spec["changes"]
        if ch.get("attendance_delta") and att.get("rate") is None:
            skip = True
        if (ch.get("academic_delta") or ch.get("completion_delta")) and not aca.get("count"):
            if ch.get("attendance_delta") or ch.get("mentorship_active"):
                ch = {k: v for k, v in ch.items() if k not in ("academic_delta", "completion_delta")}
                spec = {**spec, "changes": ch, "title": spec["title"] + " (academic layer skipped — no records)"}
            else:
                skip = True
        if skip:
            continue
        result = simulate_changes(att, aca, eng, spec["changes"], support=support, current=current)
        usable.append({**spec, **result})

    target = {"Critical": "High", "High": "Watch", "Watch": "Stable", "Stable": "Stable"}[current["category"]]
    ranked = sorted(usable, key=lambda r: (-r["delta"], len(r["changes"])))
    minimum = None
    for row in ranked:
        improved_cat = row["estimated_category"] != current["category"] and (
            {"Critical": 4, "High": 3, "Watch": 2, "Stable": 1}[row["estimated_category"]]
            < {"Critical": 4, "High": 3, "Watch": 2, "Stable": 1}[current["category"]]
        )
        if row["delta"] >= 10 or improved_cat or row["estimated_category"] == target:
            minimum = row
            break
    if not minimum and ranked:
        minimum = ranked[0]

    actions = []
    if att.get("rate") is not None and att["rate"] < 80:
        actions.append("Improve attendance — the model weights presence at 0.55 of the attendance gap.")
    if aca.get("count"):
        actions.append("Complete pending assignments / assessments recorded in the academic layer.")
        actions.append("Attend academic support for failed or low-score work.")
    if (eng.get("inactive_days") or 0) > 14:
        actions.append("Resume platform activity / class engagement.")
    actions.append("Meet an anonymous mentor (7-day counseling) if the student consents.")
    actions.append("Follow a counsellor-assigned weekly recovery plan.")

    return {
        "current": current,
        "scenarios": usable,
        "minimum_practical": minimum,
        "actions": actions,
        "label": "SIMULATED / ESTIMATED",
        "disclaimer": CAUSALITY_DISCLAIMER,
    }


def project_trajectory(att, aca, eng, support=None) -> dict:
    """7 / 30 / 60 day estimates by continuing the observed attendance window trend.

    Requires the same 12-log window used for sudden_decline. Otherwise returns
    insufficient_history instead of fabricating a curve.
    """
    current = score_student(att, aca, eng, support=support)
    decline = att.get("sudden_decline")
    if att.get("rate") is None or decline is None:
        return {
            "label": "INSUFFICIENT HISTORY",
            "current": current,
            "points": [{"days": 0, "score": current["score"], "category": current["category"]}],
            "insufficient_history": True,
            "note": "Need at least 12 attendance marks to estimate a future trajectory. No values were invented.",
        }
    # sudden_decline is older-window minus recent-window over ~6 sessions.
    # Approximate daily attendance change: decline/14 pp per day, then re-score.
    daily = float(decline) / 14.0
    points = [{"days": 0, "score": current["score"], "category": current["category"]}]
    for days in (7, 30, 60):
        delta = -daily * days  # falling attendance → negative delta to rate
        result = simulate_changes(att, aca, eng, {"attendance_delta": delta}, support=support, current=current)
        points.append({
            "days": days,
            "score": result["estimated_score"],
            "category": result["estimated_category"],
            "attendance_delta": round(delta, 1),
        })
    return {
        "label": "SIMULATED / ESTIMATED",
        "current": current,
        "points": points,
        "insufficient_history": False,
        "daily_attendance_drift_pp": round(daily, 3),
        "note": "If the recent attendance window trend continued unchanged. Not a trained time-series forecast.",
        "disclaimer": CAUSALITY_DISCLAIMER,
    }


def intervention_scenarios(att, aca, eng, support=None) -> list[dict]:
    """Faculty/admin comparison: none / attendance / full package."""
    current = score_student(att, aca, eng, support=support)
    packs = [
        {"name": "Scenario A — No intervention", "changes": {}},
        {"name": "Scenario B — Attendance +10 pp", "changes": {"attendance_delta": 10}},
        {"name": "Scenario C — Full intervention", "changes": {
            "attendance_delta": 10, "academic_delta": 10, "completion_delta": 15,
            "mentorship_active": True, "engagement_resume": True,
        }},
    ]
    out = []
    for pack in packs:
        if not pack["changes"]:
            out.append({
                "name": pack["name"],
                "estimated_score": current["score"],
                "estimated_category": current["category"],
                "direction": "unchanged",
                "label": "SIMULATED / ESTIMATED",
            })
            continue
        ch = dict(pack["changes"])
        if att.get("rate") is None:
            ch.pop("attendance_delta", None)
        if not aca.get("count"):
            ch.pop("academic_delta", None)
            ch.pop("completion_delta", None)
        result = simulate_changes(att, aca, eng, ch, support=support, current=current)
        direction = "down" if result["delta"] > 0.5 else ("up" if result["delta"] < -0.5 else "unchanged")
        out.append({
            "name": pack["name"],
            "estimated_score": result["estimated_score"],
            "estimated_category": result["estimated_category"],
            "delta": result["delta"],
            "direction": direction,
            "changes": ch,
            "label": "SIMULATED / ESTIMATED",
        })
    return out


def prioritize(rows):
    def key(r):
        cat = {"Critical": 4, "High": 3, "Watch": 2, "Stable": 1}.get(r.get("category"), 0)
        overdue = 1 if r.get("overdue") else 0
        vel = float(r.get("velocity") or 0)
        return (-cat, -overdue, -vel, -float(r.get("score") or 0))
    ranked = sorted(rows, key=key)
    for i, r in enumerate(ranked, 1):
        r["rank"] = i
        r["priority_reason"] = "Severity, SLA/overdue, then estimated velocity."
    return ranked
