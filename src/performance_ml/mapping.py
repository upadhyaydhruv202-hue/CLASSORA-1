"""Map CLASSORA student records onto benchmark features. Never invent values."""

from __future__ import annotations

from src.performance_ml.schema import FEATURES
from src.success.intelligence import predict_one
from src.success import store

ASSESSMENT_MAP = {
    "Midterm_Score": ("midterm", "mid-term", "internal"),
    "Assignments_Avg": ("assign", "homework", "coursework"),
    "Quizzes_Avg": ("quiz",),
    "Projects_Score": ("project",),
    "Participation_Score": ("particip", "engagement"),
}


def _pct(row: dict) -> float | None:
    score = row.get("score")
    max_score = row.get("max_score")
    if score is None or max_score in (None, 0, "0"):
        return None
    try:
        return round(100.0 * float(score) / float(max_score), 2)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


def _academic_by_type(records: list[dict]) -> tuple[dict, dict]:
    buckets = {key: [] for key in ASSESSMENT_MAP}
    unlabeled = []
    for row in records or []:
        label = str(row.get("assessment") or "")
        pct = _pct(row)
        if pct is None:
            continue
        hit = False
        lower = label.lower()
        for feature, keys in ASSESSMENT_MAP.items():
            if any(key in lower for key in keys):
                buckets[feature].append(pct)
                hit = True
                break
        if not hit:
            unlabeled.append(pct)
    values = {feature: _mean(vals) for feature, vals in buckets.items()}
    sources = {}
    for feature, value in values.items():
        if value is not None:
            sources[feature] = "classora_academic"
    if values.get("Midterm_Score") is None and unlabeled:
        values["Midterm_Score"] = _mean(unlabeled)
        sources["Midterm_Score"] = "classora_academic_proxy"
    return values, sources


def empty_features() -> dict:
    return {name: None for name in FEATURES}


def map_student(student_id, session=None, overrides=None, include_records=True) -> dict:
    """Return feature payload plus provenance. Missing fields stay null (imputed at inference).

    ``include_records=False`` is for Demo Calibration: only explicit overrides
    are sent to the model. Stored CLASSORA attendance/academics are not mixed in.
    """
    features = empty_features()
    sources = {name: "unavailable" for name in FEATURES}
    profile = None
    try:
        sid = int(student_id)
    except (TypeError, ValueError):
        sid = None
    if include_records and sid is not None:
        try:
            profile = predict_one(sid, session_state=session)
        except Exception:
            profile = None
    if include_records and profile:
        att = (profile.get("attendance") or {}).get("rate")
        if att is not None:
            features["Attendance (%)"] = float(att)
            sources["Attendance (%)"] = "classora_attendance"
        records = []
        try:
            records = [row for row in (store.select("academic_records") or []) if int(row.get("student_id") or 0) == sid]
        except Exception:
            records = []
        typed, typed_sources = _academic_by_type(records)
        for name, value in typed.items():
            if value is None:
                continue
            features[name] = value
            sources[name] = typed_sources.get(name, "classora_academic")
        if features["Midterm_Score"] is None:
            avg = (profile.get("academic") or {}).get("avg_score")
            if avg is not None:
                features["Midterm_Score"] = float(avg)
                sources["Midterm_Score"] = "classora_academic_proxy"
        if features["Participation_Score"] is None:
            # Engagement events are not a 0-10 participation score. Leave unavailable.
            pass
    allowed = set(FEATURES)
    for key, value in (overrides or {}).items():
        if key not in allowed or value in (None, ""):
            continue
        if key in ("Extracurricular_Activities", "Internet_Access_at_Home", "Gender", "Department", "Parent_Education_Level", "Family_Income_Level"):
            features[key] = str(value)
        else:
            try:
                features[key] = float(value)
            except (TypeError, ValueError):
                continue
        sources[key] = "optional_input"
    unavailable = [name for name, source in sources.items() if source == "unavailable"]
    return {
        "student_id": sid,
        "features": features,
        "sources": sources,
        "unavailable": unavailable,
        "mapped": [name for name, source in sources.items() if source.startswith("classora") or source == "optional_input"],
    }
