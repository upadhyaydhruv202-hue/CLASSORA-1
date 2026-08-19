"""Authoritative current-risk API. One scorer, cached per data fingerprint, RBAC-checked."""

from __future__ import annotations

from datetime import datetime, timezone

from src.success.notify import notify
from src.success.risk_model import recovery_scenarios, widget_level, widget_level_label
from src.success.twin import stored_history

_CACHE = "_risk_auth_cache"
_PROFILES = "_risk_auth_profiles"


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except Exception:
        return None


def fingerprint(profile) -> tuple:
    att = (profile or {}).get("attendance") or {}
    aca = (profile or {}).get("academic") or {}
    eng = (profile or {}).get("engagement") or {}
    pred = (profile or {}).get("prediction") or {}
    return (
        profile.get("student_id"),
        att.get("marked"),
        att.get("present"),
        att.get("rate"),
        att.get("sudden_decline"),
        att.get("consecutive_absences"),
        aca.get("count"),
        aca.get("avg_score"),
        aca.get("failed"),
        aca.get("completion"),
        eng.get("count"),
        eng.get("inactive_days"),
        bool(profile.get("mentorship_active")),
        pred.get("model_version"),
    )


def _relative(ts):
    dt = _parse(ts)
    if not dt:
        return "Updated just now"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = max(0, (_now() - dt).total_seconds())
    if seconds < 90:
        return "Updated just now"
    if seconds < 3600:
        return f"Updated {int(seconds // 60)} min ago"
    if seconds < 86400:
        return f"Updated {int(seconds // 3600)} h ago"
    return f"Updated {int(seconds // 86400)} d ago"


def _unauthorized():
    return {
        "available": False,
        "unauthorized": True,
        "riskScore": None,
        "riskLevel": None,
        "error": "Not authorized to view this risk score.",
        "lastKnown": None,
    }


def _can_read(*, actor_role, actor_student_id, actor_teacher_id, student_id) -> bool:
    if actor_role == "student":
        try:
            return actor_student_id is not None and int(actor_student_id) == int(student_id)
        except (TypeError, ValueError):
            return False
    if actor_role in ("administrator", "counsellor"):
        return True
    if actor_role == "teacher" and actor_teacher_id is not None:
        from src.database.config import is_supabase_configured, supabase
        if not is_supabase_configured():
            return False
        try:
            subjects = supabase.table("subjects").select("subject_id").eq(
                "teacher_id", int(actor_teacher_id)
            ).execute().data or []
            ids = [s["subject_id"] for s in subjects]
            if not ids:
                return False
            rows = supabase.table("subject_students").select("student_id").eq(
                "student_id", int(student_id)
            ).in_("subject_id", ids).limit(1).execute().data or []
            return bool(rows)
        except Exception:
            return False
    if actor_role in ("faculty", "mentor"):
        return True
    return False


def cached_profile(session_state, student_id):
    return ((session_state or {}).get(_PROFILES) or {}).get(student_id)


def _week_change(history, current_score):
    if current_score is None or not history:
        return None
    cutoff = _now()
    from datetime import timedelta
    oldest = None
    for row in history:
        created = _parse(row.get("created_at"))
        if not created:
            continue
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        age = cutoff - created
        if timedelta(days=5) <= age <= timedelta(days=10):
            oldest = row
            break
        if age > timedelta(days=10) and oldest is None:
            oldest = row
    if not oldest:
        if len(history) >= 2:
            oldest = history[-1]
        else:
            return None
    try:
        prev = float(oldest.get("score"))
        return round(float(current_score) - prev, 1)
    except (TypeError, ValueError):
        return None


def _persist(profile, payload):
    sid = profile.get("student_id")
    try:
        if sid is None or int(sid) < 0:
            return
    except (TypeError, ValueError):
        return
    from src.success import store
    pred = profile.get("prediction") or {}
    store.insert("risk_predictions", {
        "student_id": int(sid),
        "score": payload["riskScore"],
        "category": pred.get("category") or payload.get("modelCategory") or "Watch",
        "probability": round((payload["riskScore"] or 0) / 100.0, 3),
        "confidence": pred.get("confidence"),
        "velocity": (pred.get("temporal") or {}).get("velocity"),
        "missing_data": bool(pred.get("missing")),
        "model_version": pred.get("model_version") or "success-risk-v1.1",
        "explanation": {
            "drivers": payload.get("drivers"),
            "widgetLevel": payload.get("riskLevel"),
            "source": "risk_service",
        },
    })


def _notify_shift(student_id, previous_level, new_level, new_score, delta):
    if previous_level and new_level and previous_level != new_level:
        notify(
            role="student",
            recipient_id=student_id,
            title="Your academic-risk level has changed",
            body=(
                f"Current estimate: {new_score}%. Level: {widget_level_label(new_level)}. "
                "Open your risk widget for personalized next steps. This is not a diagnosis."
            ),
        )
        notify(
            role="counsellor",
            recipient_id="caseload",
            title="Support-risk level changed",
            body=f"Student ID {student_id}: {previous_level} → {new_level} ({new_score}%).",
        )
        return
    if delta is not None and abs(delta) >= 10:
        direction = "increased" if delta > 0 else "decreased"
        notify(
            role="student",
            recipient_id=student_id,
            title="Your academic-risk estimate moved",
            body=(
                f"Your estimate {direction} by {abs(delta)} points to {new_score}%. "
                "View recommendations from the risk widget."
            ),
        )


def get_current_risk(
    student_id,
    *,
    session_state,
    actor_role,
    actor_student_id=None,
    actor_teacher_id=None,
):
    """Return the live widget payload. Recalculates only when input fingerprint changes."""
    if not _can_read(
        actor_role=actor_role,
        actor_student_id=actor_student_id,
        actor_teacher_id=actor_teacher_id,
        student_id=student_id,
    ):
        return _unauthorized()

    cache = session_state.setdefault(_CACHE, {})
    profiles = session_state.setdefault(_PROFILES, {})
    prev_entry = cache.get(student_id) or {}
    last_payload = prev_entry.get("payload")

    try:
        from src.success.intelligence import predict_one
        profile = predict_one(student_id, session_state)
    except Exception:
        return {
            "available": False,
            "riskScore": None,
            "riskLevel": None,
            "error": "Unable to update",
            "lastKnown": last_payload,
            "updatedLabel": "Unable to update",
        }

    if not profile or not profile.get("prediction"):
        return {
            "available": False,
            "riskScore": None,
            "riskLevel": None,
            "error": "Unable to update",
            "lastKnown": last_payload,
            "updatedLabel": "Unable to update",
        }

    fp = fingerprint(profile)
    if prev_entry.get("fingerprint") == fp and last_payload and last_payload.get("available"):
        last_payload["updatedLabel"] = _relative(last_payload.get("updatedAt"))
        last_payload["displayFrom"] = last_payload.get("riskScore")
        profiles[student_id] = profile
        return last_payload

    pred = profile["prediction"]
    score = pred.get("score")
    level = pred.get("widgetLevel") or widget_level(score, pred.get("category"))
    history = stored_history(student_id, limit=20)
    previous_score = None
    previous_level = None
    if last_payload and last_payload.get("riskScore") is not None:
        previous_score = last_payload.get("riskScore")
        previous_level = last_payload.get("riskLevel")
    elif history:
        try:
            previous_score = float(history[0].get("score"))
            previous_level = widget_level(previous_score, history[0].get("category"))
        except (TypeError, ValueError):
            previous_score = None
    change = None
    if previous_score is not None and score is not None:
        change = round(float(score) - float(previous_score), 1)

    recov = recovery_scenarios(
        profile.get("attendance") or {},
        profile.get("academic") or {},
        profile.get("engagement") or {},
        support={"mentorship_active": profile.get("mentorship_active")},
    )
    payload = {
        "available": True,
        "unauthorized": False,
        "riskScore": score,
        "riskLevel": level,
        "riskLevelLabel": widget_level_label(level),
        "modelCategory": pred.get("category"),
        "previousScore": previous_score,
        "change": change,
        "weekChange": _week_change(history, score),
        "updatedAt": _now().isoformat(),
        "updatedLabel": "Updated just now",
        "drivers": pred.get("drivers") or [],
        "recommendations": recov.get("actions") or [],
        "missing": pred.get("missing") or [],
        "confidence": pred.get("confidence"),
        "disclaimer": pred.get("disclaimer"),
        "modelVersion": pred.get("model_version"),
        "history": [{"date": h.get("created_at"), "score": h.get("score"), "category": h.get("category")} for h in history[:8]],
        "displayFrom": previous_score if previous_score is not None else score,
        "error": None,
        "lastKnown": None,
    }
    profiles[student_id] = profile
    should_write = True
    if history:
        last_hist = history[0]
        try:
            same = abs(float(last_hist.get("score") or 0) - float(score or 0)) < 0.5
        except (TypeError, ValueError):
            same = False
        created = _parse(last_hist.get("created_at"))
        if same and created:
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            if (_now() - created).total_seconds() < 6 * 3600:
                should_write = False
    demo = bool(session_state.get("demo_mode"))
    if should_write and not demo:
        _persist(profile, payload)
        _notify_shift(student_id, previous_level, level, score, change)
    cache[student_id] = {"fingerprint": fp, "payload": payload}
    return payload
