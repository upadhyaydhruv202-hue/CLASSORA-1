"""AI Student Digital Twin — aggregates live attendance, academics, risk, mentorship, interventions.

Does not invent predictions. Role payloads never include another party's hidden identity.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.success import store
from src.success.risk_model import (
    CAUSALITY_DISCLAIMER,
    intervention_scenarios,
    narrative_why,
    project_trajectory,
    recovery_scenarios,
    temporal_features,
)


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def _mentorship_state(student_id):
    if student_id is None or not store.available("mentorships"):
        return {"active": False, "status": None, "identityReveal": False, "anonymousMentorId": None}
    try:
        from src.database.config import supabase
        rows = supabase.table("mentorships").select(
            "mentorship_id,status,student_alias,mentor_alias,started_at,feedback_due_at"
        ).eq("student_id", int(student_id)).order("created_at", desc=True).limit(5).execute().data or []
    except Exception:
        rows = []
    open_row = next((r for r in rows if r.get("status") in (
        "ASSIGNED", "ANONYMOUS_ACTIVE", "FEEDBACK_PENDING", "ACCEPTED", "IDENTITIES_REVEALED"
    )), None)
    row = open_row or (rows[0] if rows else None)
    if not row:
        return {"active": False, "status": None, "identityReveal": False, "anonymousMentorId": None, "history": len(rows)}
    revealed = row.get("status") in ("ACCEPTED", "IDENTITIES_REVEALED")
    return {
        "active": row.get("status") in ("ASSIGNED", "ANONYMOUS_ACTIVE", "FEEDBACK_PENDING", "ACCEPTED", "IDENTITIES_REVEALED"),
        "status": row.get("status"),
        "identityReveal": revealed,
        "anonymousMentorId": row.get("mentor_alias"),
        "anonymousStudentId": row.get("student_alias"),
        "startedAt": row.get("started_at"),
        "feedbackDueAt": row.get("feedback_due_at"),
        "history": len(rows),
    }


def _own_interventions(student_id):
    cases = [c for c in (store.select("intervention_cases") or []) if c.get("student_id") == student_id]
    recs = [r for r in (store.select("intervention_recommendations") or []) if r.get("student_id") == student_id]
    plans = [p for p in (store.select("recovery_plans") or []) if p.get("student_id") == student_id]
    tasks = [t for t in (store.select("recovery_tasks") or []) if t.get("student_id") == student_id]
    outcomes = store.select("intervention_outcomes") or []
    return {
        "cases": cases,
        "recommendations": recs,
        "plans": plans,
        "tasks": tasks,
        "open_cases": sum(1 for c in cases if c.get("status") == "open"),
        "pending_recs": sum(1 for r in recs if r.get("status") == "pending"),
        "tasks_done": sum(1 for t in tasks if t.get("done")),
        "tasks_total": len(tasks),
        "outcomes": outcomes[:20],
    }


def _timeline(profile, mentorship, interventions, logs):
    events = []
    att = profile.get("attendance") or {}
    if att.get("sudden_decline") and att["sudden_decline"] >= 10:
        events.append({"when": "Recent window", "text": f"Attendance decreased by {att['sudden_decline']} pp vs the prior window."})
    if att.get("consecutive_absences", 0) >= 3:
        events.append({"when": "Latest marks", "text": f"{att['consecutive_absences']} consecutive absences recorded."})
    aca = profile.get("academic") or {}
    if aca.get("failed"):
        events.append({"when": "Assessments", "text": f"{aca['failed']} assessment(s) below 40%."})
    pred = profile.get("prediction") or {}
    events.append({
        "when": "Now",
        "text": f"Support-risk estimate {pred.get('score')} ({pred.get('category')}).",
    })
    if mentorship.get("active"):
        events.append({"when": mentorship.get("startedAt") or "Mentorship", "text": "Anonymous mentorship is active. Identities follow student consent."})
    if mentorship.get("status") == "FEEDBACK_PENDING":
        events.append({"when": "Day 7", "text": "Mentorship feedback is available."})
    if mentorship.get("identityReveal"):
        events.append({"when": "Consent", "text": "Student accepted mentorship — identities revealed."})
    for c in (interventions.get("cases") or [])[:5]:
        events.append({"when": c.get("created_at") or "Intervention", "text": f"Intervention: {c.get('intervention_name') or c.get('status')}"})
    logs = sorted(logs or [], key=lambda r: str(r.get("timestamp") or ""))
    if len(logs) >= 2:
        last = logs[-1]
        events.append({
            "when": last.get("timestamp") or "Latest session",
            "text": "Present" if last.get("is_present") else "Absent on the most recent recorded session.",
        })
    return events[-12:]


def build_twin(profile, *, logs=None, role="staff"):
    """Assemble a Digital Twin. ``role`` filters identity and admin-only fields."""
    if not profile:
        return None
    sid = profile.get("student_id")
    att = profile.get("attendance") or {}
    aca = profile.get("academic") or {}
    eng = profile.get("engagement") or {}
    pred = profile.get("prediction") or {}
    mentorship = _mentorship_state(sid)
    support = {"mentorship_active": bool(mentorship.get("active"))}
    interventions = _own_interventions(sid)
    temporal = temporal_features(att)
    recovery = recovery_scenarios(att, aca, eng, support=support)
    trajectory = project_trajectory(att, aca, eng, support=support)
    scenarios = intervention_scenarios(att, aca, eng, support=support)
    why = narrative_why(att, aca, eng, pred, role="student" if role == "student" else "staff")
    progress = 0
    if interventions["tasks_total"]:
        progress = round(100 * interventions["tasks_done"] / interventions["tasks_total"])
    elif pred.get("category") == "Stable":
        progress = 70
    elif mentorship.get("active"):
        progress = 35

    payload = {
        "studentId": sid,
        "generatedAt": _now().isoformat(),
        "disclaimer": CAUSALITY_DISCLAIMER,
        "overview": {
            "riskScore": pred.get("score"),
            "category": pred.get("category"),
            "widgetLevel": pred.get("widgetLevel"),
            "confidence": pred.get("confidence"),
            "status": pred.get("category"),
            "temporal": temporal,
        },
        "academic": aca,
        "attendance": att,
        "engagement": eng,
        "risk": {
            "score": pred.get("score"),
            "category": pred.get("category"),
            "trend": temporal["pattern"],
            "drivers": pred.get("drivers") or [],
            "contributors": pred.get("contributors") or [],
            "missing": pred.get("missing") or [],
            "modelVersion": pred.get("model_version"),
            "why": why,
        },
        "intervention": {
            "openCases": interventions["open_cases"],
            "pendingRecommendations": interventions["pending_recs"],
            "recoveryProgress": progress,
            "tasksDone": interventions["tasks_done"],
            "tasksTotal": interventions["tasks_total"],
        },
        "mentorship": {
            "status": mentorship.get("status") or "NONE",
            "active": mentorship.get("active"),
            "identityReveal": mentorship.get("identityReveal"),
            "anonymousMentorId": mentorship.get("anonymousMentorId") if role == "student" else mentorship.get("anonymousStudentId") or mentorship.get("anonymousMentorId"),
        },
        "recovery": recovery,
        "trajectory": trajectory,
        "scenarios": scenarios,
        "timeline": _timeline(profile, mentorship, interventions, logs),
        "method": why.get("method"),
    }
    if role == "student":
        payload["displayName"] = profile.get("name")
        payload.pop("scenarios", None)
    elif role in ("faculty", "mentor"):
        payload["displayName"] = profile.get("name")
        payload["mentorship"]["anonymousStudentId"] = mentorship.get("anonymousStudentId")
    else:
        payload["displayName"] = profile.get("name")
        payload["courses"] = profile.get("courses")
    return payload


def persist_snapshot(twin, *, demo=False):
    if not twin or demo:
        return None
    sid = twin.get("studentId")
    try:
        if sid is None or int(sid) < 0:
            return None
    except (TypeError, ValueError):
        return None
    risk = twin.get("risk") or {}
    overview = twin.get("overview") or {}
    explanation = {
        "drivers": risk.get("drivers"),
        "why": (risk.get("why") or {}).get("why"),
        "temporal": overview.get("temporal"),
        "trajectory": (twin.get("trajectory") or {}).get("points"),
        "insufficient_history": (twin.get("trajectory") or {}).get("insufficient_history"),
    }
    return store.insert("risk_predictions", {
        "student_id": int(sid),
        "score": risk.get("score") or 0,
        "category": risk.get("category") or "Watch",
        "probability": round((risk.get("score") or 0) / 100.0, 3),
        "confidence": overview.get("confidence"),
        "velocity": (overview.get("temporal") or {}).get("velocity"),
        "missing_data": bool(risk.get("missing")),
        "model_version": risk.get("modelVersion") or "success-risk-v1.1",
        "explanation": explanation,
    })


def stored_history(student_id, limit=12):
    if student_id is None:
        return []
    rows = [r for r in (store.select("risk_predictions") or []) if r.get("student_id") == student_id]
    rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
    return rows[:limit]


def sync_once(profiles, logs_by, *, demo=False, role="staff"):
    """Persist twins that moved ≥1 point since the last stored snapshot."""
    if demo:
        return 0
    written = 0
    for p in profiles or []:
        hist = stored_history(p.get("student_id"), limit=1)
        last = hist[0] if hist else None
        twin = build_twin(p, logs=logs_by.get(p.get("student_id")), role=role)
        if not twin:
            continue
        score = (twin.get("risk") or {}).get("score")
        if last and abs(float(last.get("score") or 0) - float(score or 0)) < 1:
            created = _parse(last.get("created_at"))
            if created and _now() - created < timedelta(hours=12):
                continue
        if persist_snapshot(twin, demo=demo):
            written += 1
            from src.success.notify import maybe_notify_risk
            maybe_notify_risk(p, last)
    return written
