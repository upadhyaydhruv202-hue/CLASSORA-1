"""Institutional dropout root-cause engine.

Uses explicit student academic outcomes. Does not invent dropouts from risk scores.
Association language only — no causal claims, no faculty blame, no fabricated finance.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from src.cohort.engine import parse_ts
from src.cohort.stats import finite, mean, safe_div
from src.dropout import stats as S

ANALYSIS_VERSION = "dropout-root-v1.0"

DROPOUT_STATUSES = frozenset({"DROPPED_OUT", "WITHDRAWN", "DISCONTINUED"})
RETAINED_STATUSES = frozenset({"ACTIVE", "GRADUATED", "TRANSFERRED"})
ALL_OUTCOME_STATUSES = tuple(sorted(DROPOUT_STATUSES | RETAINED_STATUSES))

FIRST_YEAR_SEMESTERS = frozenset({
    "1", "2", "sem_1", "sem_2", "semester 1", "semester 2", "sem1", "sem2", "year_1",
})

DEFAULT_CONFIG = {
    "min_factor_sample_size": 10,
    "min_dropout_observations": 10,
    "min_periods": 1,
    "suppress_group_size": 5,
    "low_attendance_threshold": 60.0,
    "low_completion_threshold": 70.0,
    "fail_mark": 40.0,
    "high_rate_threshold": 15.0,
    "high_volume_threshold": 20,
    "attendance_lookback_only": True,
}

CAUSALITY_DISCLAIMER = (
    "These are associated factors from institutional outcomes, not proven causes. "
    "They do not assign responsibility to a faculty member, department, course, student, or external event."
)

FINANCIAL_UNAVAILABLE = (
    "Financial instability analysis requires financial-aid or fee-related data that is not currently available."
)

DEPARTMENT_UNAVAILABLE = (
    "CLASSORA has no department table. Organizational drill-down uses subject section, which is the grouping that exists."
)

RECOMMENDATIONS = {
    "LOW_ATTENDANCE": "Consider an attendance-focused early intervention program for affected cohorts.",
    "ACADEMIC_FAILURE": "Consider additional academic support, remedial sessions, or subject-level interventions.",
    "REPEATED_FAILURE": "Consider targeted support for students with repeated subject failure or backlogs.",
    "DECLINING_MARKS": "Consider academic monitoring where marks have declined relative to earlier assessments.",
    "LOW_ASSIGNMENT": "Consider structured assignment support and completion monitoring.",
    "FIRST_YEAR": "Consider strengthening first-year orientation, foundational support, and early academic monitoring.",
    "COURSE_DIFFICULTY": "Consider reviewing course-level failure, assessment, attendance, and support patterns.",
    "LOW_ENGAGEMENT": "Consider engagement check-ins for cohorts with declining platform activity.",
    "SEMESTER_CONCENTRATION": "Consider additional support in semesters that concentrate observed dropout outcomes.",
}


def normalize_config(raw=None):
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in cfg or value is None or value == "":
                continue
            try:
                cfg[key] = type(cfg[key])(value) if not isinstance(cfg[key], bool) else bool(value)
            except (TypeError, ValueError):
                continue
    cfg["min_factor_sample_size"] = max(1, int(cfg["min_factor_sample_size"]))
    cfg["min_dropout_observations"] = max(1, int(cfg["min_dropout_observations"]))
    cfg["suppress_group_size"] = max(1, int(cfg["suppress_group_size"]))
    return cfg


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _norm_sem(value):
    return str(value or "").strip().lower().replace("-", "_")


def is_first_year_semester(value):
    return _norm_sem(value) in FIRST_YEAR_SEMESTERS


def is_dropout_status(status):
    return str(status or "").strip().upper() in DROPOUT_STATUSES


def latest_outcomes(rows):
    latest = {}
    for row in rows or []:
        sid = _int(row.get("student_id"))
        if sid is None:
            continue
        status = str(row.get("status") or "").strip().upper()
        if status not in ALL_OUTCOME_STATUSES:
            continue
        ts = parse_ts(row.get("recorded_at") or row.get("created_at")) or datetime.min
        prev = latest.get(sid)
        if prev is None or ts >= prev["ts"]:
            latest[sid] = {
                "student_id": sid,
                "status": status,
                "period": str(row.get("period") or "").strip() or None,
                "recorded_at": ts if ts != datetime.min else None,
                "ts": ts,
                "dropped": status in DROPOUT_STATUSES,
            }
    return latest


def _subject_map(bundle):
    out = {}
    for row in bundle.get("subjects") or []:
        sid = _int(row.get("subject_id"))
        if sid is None:
            continue
        out[sid] = {
            "subject_id": sid,
            "name": row.get("name") or row.get("subject_code") or f"Course {sid}",
            "subject_code": row.get("subject_code") or "",
            "section": (row.get("section") or "").strip() or "—",
            "teacher_id": _int(row.get("teacher_id")),
        }
    return out


def _cutoff(outcome):
    return outcome.get("recorded_at") if outcome else None


def _before(ts, cutoff):
    if cutoff is None or ts is None:
        return True
    return ts <= cutoff


def build_profiles(bundle, config):
    subjects = _subject_map(bundle)
    outcomes = latest_outcomes(bundle.get("outcomes") or [])
    enroll_by = defaultdict(list)
    for row in bundle.get("enrollments") or []:
        sid = _int(row.get("student_id"))
        sub = _int(row.get("subject_id"))
        if sid is None or sub is None or sub not in subjects:
            continue
        enroll_by[sid].append(sub)

    att_by = defaultdict(list)
    for row in bundle.get("attendance") or []:
        sid = _int(row.get("student_id"))
        ts = parse_ts(row.get("timestamp"))
        if sid is None or ts is None:
            continue
        att_by[sid].append({"ts": ts, "present": bool(row.get("is_present")), "subject_id": _int(row.get("subject_id"))})

    aca_by = defaultdict(list)
    for row in bundle.get("academic") or []:
        sid = _int(row.get("student_id"))
        ts = parse_ts(row.get("recorded_at") or row.get("created_at"))
        if sid is None:
            continue
        score = finite(row.get("score"))
        max_score = finite(row.get("max_score"))
        pct = safe_div(100.0 * score, max_score) if score is not None and max_score else None
        aca_by[sid].append({
            "ts": ts,
            "pct": pct,
            "backlog": bool(row.get("backlog")),
            "semester": row.get("semester"),
            "subject_id": _int(row.get("subject_id")),
            "scored": pct is not None,
        })

    lms_by = defaultdict(list)
    for row in bundle.get("lms") or []:
        sid = _int(row.get("student_id"))
        ts = parse_ts(row.get("occurred_at") or row.get("timestamp"))
        if sid is None or ts is None:
            continue
        lms_by[sid].append(ts)

    known = set()
    for row in bundle.get("students") or []:
        sid = _int(row.get("student_id"))
        if sid is not None:
            known.add(sid)
    known |= set(enroll_by) | set(outcomes)

    profiles = []
    for sid in sorted(known):
        outcome = outcomes.get(sid)
        cutoff = _cutoff(outcome) if config.get("attendance_lookback_only") else None
        logs = [r for r in att_by.get(sid) or [] if _before(r["ts"], cutoff)]
        recs = [r for r in aca_by.get(sid) or [] if r["ts"] is None or _before(r["ts"], cutoff)]
        events = [t for t in lms_by.get(sid) or [] if _before(t, cutoff)]
        present = sum(1 for r in logs if r["present"])
        att_rate = round(100.0 * present / len(logs), 1) if logs else None
        streak = 0
        for r in sorted(logs, key=lambda item: item["ts"], reverse=True):
            if r["present"]:
                break
            streak += 1
        scored = [r["pct"] for r in recs if r.get("scored")]
        failed = sum(1 for pct in scored if pct < config["fail_mark"])
        backlogs = sum(1 for r in recs if r.get("backlog"))
        avg_marks = round(mean(scored), 1) if scored else None
        completion = round(100.0 * len(scored) / len(recs), 1) if recs else None
        if len(scored) >= 4:
            older, newer = mean(scored[: len(scored) // 2]), mean(scored[len(scored) // 2:])
            decline = (older - newer) if older is not None and newer is not None else None
        else:
            decline = None
        semesters = {_norm_sem(r.get("semester")) for r in recs if r.get("semester")}
        first_year = any(is_first_year_semester(s) for s in semesters)
        courses = enroll_by.get(sid) or []
        sections = {subjects[c]["section"] for c in courses if c in subjects}
        profiles.append({
            "student_id": sid,
            "dropped": bool(outcome and outcome["dropped"]),
            "status": (outcome or {}).get("status") or "ACTIVE",
            "period": (outcome or {}).get("period") or ((outcome or {}).get("recorded_at").year if outcome and outcome.get("recorded_at") else None),
            "recorded_at": (outcome or {}).get("recorded_at"),
            "attendance": att_rate,
            "consecutive": streak,
            "avg_marks": avg_marks,
            "failed": failed,
            "backlogs": backlogs,
            "completion": completion,
            "decline": decline,
            "engagement": len(events) if events else (0 if (bundle.get("lms") or []) else None),
            "first_year": first_year,
            "semesters": [s for s in semesters if s],
            "courses": courses,
            "sections": sorted(sections),
            "has_attendance": bool(logs),
            "has_academic": bool(recs),
            "has_lms": bool(events) or None,
        })
    return profiles, subjects


def _flag_low_attendance(p, cfg):
    return p["attendance"] is not None and p["attendance"] < cfg["low_attendance_threshold"]


def _flag_academic_failure(p, cfg):
    if p["failed"]:
        return True
    return p["avg_marks"] is not None and p["avg_marks"] < cfg["fail_mark"]


def _flag_repeated(p, _cfg):
    return (p["failed"] or 0) >= 2 or (p["backlogs"] or 0) >= 2


def _flag_decline(p, _cfg):
    return p["decline"] is not None and p["decline"] >= 8


def _flag_assignment(p, cfg):
    return p["completion"] is not None and p["completion"] < cfg["low_completion_threshold"]


def _flag_first_year(p, _cfg):
    return bool(p["first_year"])


def _flag_engagement(p, _cfg):
    if p["engagement"] is None:
        return None
    return p["engagement"] == 0


FACTORS = (
    ("LOW_ATTENDANCE", "Attendance", "Students with persistently low attendance", _flag_low_attendance, "has_attendance"),
    ("ACADEMIC_FAILURE", "Academic", "Students with failed assessments or very low average marks", _flag_academic_failure, "has_academic"),
    ("REPEATED_FAILURE", "Academic", "Students with repeated failures or backlogs", _flag_repeated, "has_academic"),
    ("DECLINING_MARKS", "Academic", "Students whose later marks are lower than earlier marks", _flag_decline, "has_academic"),
    ("LOW_ASSIGNMENT", "Assignment", "Students with low assessment/assignment completion", _flag_assignment, "has_academic"),
    ("FIRST_YEAR", "Cohort", "Students associated with semester 1–2 records", _flag_first_year, None),
    ("LOW_ENGAGEMENT", "Engagement", "Students with no recorded platform activity", _flag_engagement, "has_lms"),
)


def _table(profiles, exposed_fn, cfg):
    exposed = []
    comparison = []
    unavailable = 0
    for p in profiles:
        flag = exposed_fn(p, cfg)
        if flag is None:
            unavailable += 1
            continue
        (exposed if flag else comparison).append(p)
    return exposed, comparison, unavailable


def _counts(group):
    n = len(group)
    d = sum(1 for p in group if p["dropped"])
    return n, d, S.dropout_rate(d, n)


def evaluate_factor(code, title, factor_type, description, exposed, comparison, baseline_rate, cfg, trends=None):
    exp_n, exp_d, exp_rate = _counts(exposed)
    cmp_n, cmp_d, cmp_rate = _counts(comparison)
    min_n = cfg["min_factor_sample_size"]
    if exp_n < min_n or cmp_n < min_n:
        return {
            "factorId": code,
            "factorName": title,
            "factorType": factor_type,
            "description": description,
            "available": True,
            "classification": "INSUFFICIENT_DATA",
            "confidence": "INSUFFICIENT_DATA",
            "evidence": "Insufficient sample size for reliable institutional analysis.",
            "affectedStudents": exp_n,
            "totalStudents": exp_n + cmp_n,
            "dropoutRate": exp_rate,
            "comparisonRate": cmp_rate,
            "baselineDropoutRate": baseline_rate,
            "relativeRisk": None,
            "riskDifference": None,
            "supportedData": True,
        }
    rr = S.relative_risk(exp_rate, cmp_rate)
    rd = S.risk_difference(exp_rate, cmp_rate)
    a, b, c, d = exp_d, exp_n - exp_d, cmp_d, cmp_n - cmp_d
    p_value, test = S.association_p(a, b, c, d)
    oratio = S.odds_ratio(a, b, c, d)
    conf = S.confidence_label(
        exposed_n=exp_n, comparison_n=cmp_n, p_value=p_value,
        min_n=min_n, relative_risk=rr, risk_diff=rd,
    )
    series = [row.get("rate") for row in (trends or [])]
    trend = S.classify_trend(series) if series else "STABLE"
    classification = S.classify_factor(relative_risk=rr, risk_diff=rd, trend=trend, confidence=conf)
    evidence = (
        f"Among students in the {title.lower()} group, the observed dropout rate was "
        f"{exp_rate}%, compared with {cmp_rate}% in the comparison group and {baseline_rate}% institution-wide. "
        f"This is an association of {rd:+.1f} percentage points"
        + (f" and a relative risk of {rr}×" if rr is not None else "")
        + ". This is not a confirmed cause."
    )
    return {
        "factorId": code,
        "factorName": title,
        "factorType": factor_type,
        "description": description,
        "available": True,
        "classification": classification,
        "confidence": conf,
        "trend": trend,
        "affectedStudents": exp_n,
        "affectedDropouts": exp_d,
        "comparisonStudents": cmp_n,
        "comparisonDropouts": cmp_d,
        "totalStudents": exp_n + cmp_n,
        "affectedPercentage": round(100.0 * exp_n / max(1, exp_n + cmp_n), 1),
        "dropoutRate": exp_rate,
        "comparisonRate": cmp_rate,
        "baselineDropoutRate": baseline_rate,
        "relativeRisk": rr,
        "riskDifference": rd,
        "oddsRatio": oratio,
        "pValue": p_value,
        "test": test,
        "evidence": evidence,
        "supportedData": True,
        "confirmedCause": False,
    }


def _period_key(profile):
    if profile.get("period"):
        return str(profile["period"])
    rec = profile.get("recorded_at")
    if rec:
        return str(rec.year)
    return "unspecified"


def factor_trends(profiles, exposed_fn, cfg):
    by_period = defaultdict(list)
    for p in profiles:
        by_period[_period_key(p)].append(p)
    rows = []
    for period in sorted(by_period):
        if period == "unspecified" and len(by_period) > 1:
            continue
        exposed, comparison, _u = _table(by_period[period], exposed_fn, cfg)
        if len(exposed) < cfg["suppress_group_size"]:
            continue
        _n, _d, rate = _counts(exposed)
        rows.append({"period": period, "rate": rate, "students": len(exposed), "dropouts": _d})
    return rows


def slice_groups(profiles, subjects, cfg):
    sections = defaultdict(list)
    semesters = defaultdict(list)
    courses = defaultdict(list)
    for p in profiles:
        for section in p["sections"] or ["—"]:
            sections[section].append(p)
        for sem in p["semesters"] or []:
            semesters[sem].append(p)
        if not p["semesters"]:
            semesters["unspecified"].append(p)
        for cid in p["courses"]:
            courses[cid].append(p)

    def _rows(mapping, kind, label_fn):
        out = []
        for key, group in mapping.items():
            n, d, rate = _counts(group)
            suppressed = n < cfg["suppress_group_size"]
            out.append({
                "id": str(key),
                "kind": kind,
                "label": "Data suppressed due to small cohort size." if suppressed else label_fn(key),
                "students": None if suppressed else n,
                "dropouts": None if suppressed else d,
                "dropoutRate": None if suppressed else rate,
                "suppressed": suppressed,
                "volume": d,
                "rate": rate or 0,
            })
        out.sort(key=lambda row: (-(row.get("volume") or 0), -(row.get("rate") or 0)))
        return out

    section_rows = _rows(sections, "section", lambda k: f"Section {k}")
    semester_rows = _rows({k: v for k, v in semesters.items() if k != "unspecified" or len(semesters) == 1}, "semester", lambda k: f"Semester {k}")
    course_rows = _rows(courses, "course", lambda k: (subjects.get(int(k)) or {}).get("name") or f"Course {k}")
    for row in course_rows:
        if row.get("suppressed"):
            continue
        sub = subjects.get(_int(row["id"])) or {}
        row["section"] = sub.get("section")
        row["subjectCode"] = sub.get("subject_code")
    return {"sections": section_rows, "semesters": semester_rows, "courses": course_rows}


def heatmap(profiles, cfg):
    cells = defaultdict(lambda: {"n": 0, "d": 0})
    for p in profiles:
        secs = p["sections"] or ["—"]
        sems = p["semesters"] or ["unspecified"]
        for section in secs:
            for sem in sems:
                cells[(section, sem)]["n"] += 1
                if p["dropped"]:
                    cells[(section, sem)]["d"] += 1
    rows = []
    for (section, sem), val in sorted(cells.items()):
        suppressed = val["n"] < cfg["suppress_group_size"]
        rows.append({
            "section": section,
            "semester": sem,
            "students": None if suppressed else val["n"],
            "dropouts": None if suppressed else val["d"],
            "dropoutRate": None if suppressed else S.dropout_rate(val["d"], val["n"]),
            "suppressed": suppressed,
        })
    return rows


def intersections(profiles, cfg):
    pairs = (
        ("LOW_ATTENDANCE", "ACADEMIC_FAILURE", _flag_low_attendance, _flag_academic_failure),
        ("LOW_ATTENDANCE", "LOW_ASSIGNMENT", _flag_low_attendance, _flag_assignment),
        ("ACADEMIC_FAILURE", "REPEATED_FAILURE", _flag_academic_failure, _flag_repeated),
    )
    out = []
    for a, b, fa, fb in pairs:
        both = [p for p in profiles if fa(p, cfg) is True and fb(p, cfg) is True]
        if len(both) < cfg["min_factor_sample_size"]:
            out.append({
                "id": f"{a}+{b}",
                "factors": [a, b],
                "classification": "INSUFFICIENT_DATA",
                "evidence": "Insufficient sample size for this factor combination.",
            })
            continue
        n, d, rate = _counts(both)
        others = [p for p in profiles if p not in both]
        _on, _od, other_rate = _counts(others)
        rr = S.relative_risk(rate, other_rate)
        rd = S.risk_difference(rate, other_rate)
        out.append({
            "id": f"{a}+{b}",
            "factors": [a, b],
            "students": n,
            "dropouts": d,
            "dropoutRate": rate,
            "comparisonRate": other_rate,
            "relativeRisk": rr,
            "riskDifference": rd,
            "evidence": (
                f"Students exhibiting both {a.replace('_', ' ').lower()} and {b.replace('_', ' ').lower()} "
                f"had an observed dropout rate of {rate}%, compared with {other_rate}% among other students. "
                "This is an association, not a confirmed cause."
            ),
        })
    return out


def course_difficulty(profiles, subjects, cfg, baseline_rate):
    by_course = defaultdict(list)
    for p in profiles:
        for cid in p["courses"]:
            by_course[cid].append(p)
    out = []
    for cid, group in by_course.items():
        others = [p for p in profiles if cid not in (p["courses"] or [])]
        if len(group) < cfg["min_factor_sample_size"] or len(others) < cfg["min_factor_sample_size"]:
            continue
        n, d, rate = _counts(group)
        _on, _od, other_rate = _counts(others)
        fail_share = mean([1.0 if _flag_academic_failure(p, cfg) else 0.0 for p in group if p["has_academic"]])
        att = mean([p["attendance"] for p in group if p["attendance"] is not None])
        rr = S.relative_risk(rate, other_rate)
        rd = S.risk_difference(rate, other_rate)
        if (rd or 0) < 5 and (rr or 1) < 1.3:
            continue
        sub = subjects.get(cid) or {}
        out.append({
            "factorId": f"COURSE_{cid}",
            "factorName": f"Course concentration — {sub.get('name') or cid}",
            "factorType": "Course",
            "subjectId": cid,
            "subjectName": sub.get("name"),
            "section": sub.get("section"),
            "affectedStudents": n,
            "affectedDropouts": d,
            "dropoutRate": rate,
            "comparisonRate": other_rate,
            "baselineDropoutRate": baseline_rate,
            "relativeRisk": rr,
            "riskDifference": rd,
            "averageAttendance": att,
            "failureShare": round(100.0 * fail_share, 1) if fail_share is not None else None,
            "available": True,
            "classification": S.classify_factor(relative_risk=rr, risk_diff=rd, trend="STABLE", confidence="MODERATE"),
            "confidence": "MODERATE",
            "supportedData": True,
            "confirmedCause": False,
            "evidence": (
                f"Dropout concentration is higher among students associated with this course "
                f"({rate}% observed vs {other_rate}% among students not enrolled in it). "
                "This is not a finding that the course or faculty caused dropout."
            ),
        })
    out.sort(key=lambda row: (-(row.get("riskDifference") or 0), -(row.get("affectedDropouts") or 0)))
    return out[:8]


def multivariate(profiles, cfg):
    names = ["low_attendance", "academic_failure", "repeated_failure", "low_assignment", "first_year"]
    rows = []
    for p in profiles:
        if p["attendance"] is None and not p["has_academic"]:
            continue
        rows.append({
            "low_attendance": 1.0 if _flag_low_attendance(p, cfg) else 0.0,
            "academic_failure": 1.0 if _flag_academic_failure(p, cfg) else 0.0,
            "repeated_failure": 1.0 if _flag_repeated(p, cfg) else 0.0,
            "low_assignment": 1.0 if _flag_assignment(p, cfg) else 0.0,
            "first_year": 1.0 if p["first_year"] else 0.0,
            "y": 1 if p["dropped"] else 0,
        })
    if len(rows) < 30 or sum(r["y"] for r in rows) < 5:
        return {"available": False, "reason": "Insufficient labeled outcomes for a stable multivariate model."}
    mid = max(8, int(len(rows) * 0.7))
    train, test = rows[:mid], rows[mid:]
    model = S.logistic_fit(train, names)
    if not model:
        return {"available": False, "reason": "The logistic model could not be fit on the available sample."}
    pairs = []
    for row in (test or train):
        prob = S.predict_proba(row, model, names)
        if prob is not None:
            pairs.append((prob, row["y"]))
    metrics = S.classification_metrics(pairs)
    importance = sorted(
        ({"name": k, "coefficient": v, "direction": "higher_dropout_odds" if v > 0 else "lower_dropout_odds"}
         for k, v in (model.get("coefficients") or {}).items()),
        key=lambda item: -abs(item["coefficient"]),
    )
    return {
        "available": True,
        "model": "l2_logistic",
        "version": ANALYSIS_VERSION,
        "coefficients": model.get("coefficients"),
        "intercept": model.get("intercept"),
        "importance": importance,
        "validation": metrics,
        "note": "Coefficients are log-odds associations from a regularized logistic model. They are not causal effects. Features use records at or before the outcome date when that date exists.",
    }


def priority_cell(rate, volume, cfg):
    high_rate = (rate or 0) >= cfg["high_rate_threshold"]
    high_vol = (volume or 0) >= cfg["high_volume_threshold"]
    if high_rate and high_vol:
        return "CRITICAL"
    if high_rate and not high_vol:
        return "TARGETED"
    if (not high_rate) and high_vol:
        return "BROAD"
    return "MONITOR"


def recommendations(factors):
    ranked = []
    for factor in factors or []:
        if not factor.get("available") or factor.get("classification") in ("INSUFFICIENT_DATA",):
            continue
        if (factor.get("relativeRisk") or 1) < 1.2 and (factor.get("riskDifference") or 0) < 5:
            continue
        rec = RECOMMENDATIONS.get(factor.get("factorId") or "")
        if factor.get("factorId", "").startswith("COURSE_"):
            rec = RECOMMENDATIONS["COURSE_DIFFICULTY"]
        if not rec:
            continue
        weight = (factor.get("affectedDropouts") or 0) * (factor.get("relativeRisk") or 1)
        ranked.append({
            "priority": 0,
            "factorId": factor.get("factorId"),
            "title": factor.get("factorName"),
            "recommendation": rec,
            "weight": weight,
            "note": "Decision-support suggestion only. CLASSORA does not execute institutional actions.",
        })
    ranked.sort(key=lambda row: -row["weight"])
    for i, row in enumerate(ranked, 1):
        row["priority"] = i
        row.pop("weight", None)
    return ranked[:6]


def story(overview, factors, slices):
    top = next((f for f in factors if f.get("available") and f.get("classification") not in ("INSUFFICIENT_DATA",)), None)
    first = next((f for f in factors if f.get("factorId") == "FIRST_YEAR" and f.get("available")), None)
    section = (slices.get("sections") or [None])[0]
    bits = [
        f"In the analyzed period the institutional observed dropout rate was {overview.get('dropoutRate')}% "
        f"({overview.get('dropouts')} of {overview.get('enrolled')} students)."
    ]
    if overview.get("previousRate") is not None and overview.get("changePp") is not None:
        bits.append(f"The previous comparable rate was {overview['previousRate']}% ({overview['changePp']:+.1f} pp).")
    if first and (first.get("relativeRisk") or 0) >= 1.3:
        bits.append(
            "First-year / early-semester records show a higher observed dropout rate than later stages. "
            "This is a concentration pattern, not a confirmed cause."
        )
    if top:
        bits.append(top.get("evidence") or "")
    if section and not section.get("suppressed"):
        bits.append(
            f"The largest available organizational grouping by volume is {section.get('label')} "
            f"({section.get('dropouts')} observed outcomes)."
        )
    bits.append(CAUSALITY_DISCLAIMER)
    return " ".join(b for b in bits if b)


def analyze(bundle, config=None):
    cfg = normalize_config(config)
    profiles, subjects = build_profiles(bundle, cfg)
    enrolled = len(profiles)
    dropouts = sum(1 for p in profiles if p["dropped"])
    labeled = sum(1 for p in (bundle.get("outcomes") or []) if str(p.get("status") or "").upper() in ALL_OUTCOME_STATUSES)
    baseline = S.dropout_rate(dropouts, enrolled)
    data_quality = {
        "students": enrolled,
        "explicitOutcomes": labeled,
        "dropouts": dropouts,
        "attendanceRecords": len(bundle.get("attendance") or []),
        "academicRecords": len(bundle.get("academic") or []),
        "lmsRecords": len(bundle.get("lms") or []),
        "financialRecords": 0,
        "departmentDimension": False,
        "yearDimension": False,
        "semesterDimension": any(p["semesters"] for p in profiles),
        "sectionDimension": any(p["sections"] for p in profiles),
    }
    unavailable = {
        "FINANCIAL": {"available": False, "reason": FINANCIAL_UNAVAILABLE, "status": "NOT_AVAILABLE"},
        "DEPARTMENT": {"available": False, "reason": DEPARTMENT_UNAVAILABLE, "status": "NOT_AVAILABLE"},
        "YEAR": {"available": False, "reason": "CLASSORA has no student year field. First-year analysis uses semester 1–2 labels when present.", "status": "NOT_AVAILABLE"},
    }
    if enrolled == 0:
        return {
            "version": ANALYSIS_VERSION,
            "insufficient": True,
            "reason": "Insufficient historical dropout data for reliable institutional root-cause analysis.",
            "overview": {"enrolled": 0, "dropouts": 0, "dropoutRate": None},
            "factors": [],
            "unavailable": unavailable,
            "disclaimer": CAUSALITY_DISCLAIMER,
            "dataQuality": data_quality,
        }
    if dropouts < cfg["min_dropout_observations"]:
        return {
            "version": ANALYSIS_VERSION,
            "insufficient": True,
            "reason": "Insufficient historical dropout data for reliable institutional root-cause analysis.",
            "overview": {"enrolled": enrolled, "dropouts": dropouts, "dropoutRate": baseline},
            "factors": [],
            "unavailable": unavailable,
            "disclaimer": CAUSALITY_DISCLAIMER,
            "dataQuality": data_quality,
        }

    by_period = defaultdict(list)
    for p in profiles:
        by_period[_period_key(p)].append(p)
    period_rates = []
    for period in sorted(k for k in by_period if k != "unspecified" or len(by_period) == 1):
        n, d, rate = _counts(by_period[period])
        if n >= cfg["suppress_group_size"]:
            period_rates.append({"period": period, "students": n, "dropouts": d, "dropoutRate": rate})
    previous = period_rates[-2]["dropoutRate"] if len(period_rates) >= 2 else None
    change = S.risk_difference(baseline, previous) if previous is not None else None

    factors = []
    for code, ftype, desc, fn, need in FACTORS:
        if need == "has_lms" and not (bundle.get("lms") or []):
            unavailable["LOW_ENGAGEMENT"] = {
                "available": False,
                "reason": "Platform activity is not stored, so engagement is not analyzed.",
                "status": "NOT_AVAILABLE",
            }
            continue
        if need == "has_academic" and not (bundle.get("academic") or []):
            unavailable[code] = {"available": False, "reason": "Academic records are not available.", "status": "NOT_AVAILABLE"}
            continue
        if need == "has_attendance" and not (bundle.get("attendance") or []):
            unavailable[code] = {"available": False, "reason": "Attendance data unavailable.", "status": "NOT_AVAILABLE"}
            continue
        if code == "FIRST_YEAR" and not any(p["first_year"] for p in profiles):
            unavailable["FIRST_YEAR"] = {
                "available": False,
                "reason": "First-year analysis needs semester 1–2 labels on academic records. Those labels are not present.",
                "status": "NOT_AVAILABLE",
            }
            continue
        exposed, comparison, _u = _table(profiles, fn, cfg)
        trends = factor_trends(profiles, fn, cfg)
        title = {
            "LOW_ATTENDANCE": "Low attendance",
            "ACADEMIC_FAILURE": "Academic failure",
            "REPEATED_FAILURE": "Repeated academic failure",
            "DECLINING_MARKS": "Declining marks",
            "LOW_ASSIGNMENT": "Assignment non-completion",
            "FIRST_YEAR": "First-year / early-semester concentration",
            "LOW_ENGAGEMENT": "Low platform activity",
        }[code]
        item = evaluate_factor(code, title, ftype, desc, exposed, comparison, baseline, cfg, trends)
        item["trends"] = trends
        item["drilldown"] = _factor_drill(exposed, subjects, cfg)
        factors.append(item)

    course_factors = course_difficulty(profiles, subjects, cfg, baseline)
    factors.extend(course_factors)
    ranked = [f for f in factors if f.get("available")]
    ranked.sort(key=lambda f: (-(f.get("relativeRisk") or 0), -(f.get("riskDifference") or 0), -(f.get("affectedDropouts") or 0)))
    if ranked and all((f.get("classification") in ("STABLE", "INSUFFICIENT_DATA") and (f.get("relativeRisk") or 1) < 1.3) for f in ranked):
        no_dominant = True
    else:
        no_dominant = not any((f.get("relativeRisk") or 1) >= 1.3 or (f.get("riskDifference") or 0) >= 8 for f in ranked if f.get("classification") != "INSUFFICIENT_DATA")

    slices = slice_groups(profiles, subjects, cfg)
    for group in slices.values():
        for row in group:
            if row.get("suppressed"):
                continue
            row["vsInstitution"] = S.risk_difference(row.get("dropoutRate"), baseline)
            row["priority"] = priority_cell(row.get("dropoutRate"), row.get("dropouts"), cfg)
    top_section = next((r for r in slices["sections"] if not r.get("suppressed")), None)
    top_semester = next((r for r in slices["semesters"] if not r.get("suppressed")), None)
    top_course = next((r for r in slices["courses"] if not r.get("suppressed")), None)
    top_factor = next((f for f in ranked if f.get("classification") not in ("INSUFFICIENT_DATA",)), None)

    overview = {
        "enrolled": enrolled,
        "dropouts": dropouts,
        "retained": enrolled - dropouts,
        "dropoutRate": baseline,
        "previousRate": previous,
        "changePp": change,
        "highestSection": top_section,
        "highestSemester": top_semester,
        "highestCourse": top_course,
        "topFactor": {"factorId": top_factor.get("factorId"), "factorName": top_factor.get("factorName")} if top_factor else None,
    }
    first_year_share = None
    fy = next((f for f in factors if f.get("factorId") == "FIRST_YEAR" and f.get("affectedDropouts") is not None), None)
    if fy and dropouts:
        first_year_share = round(100.0 * (fy.get("affectedDropouts") or 0) / dropouts, 1)

    payload = {
        "version": ANALYSIS_VERSION,
        "insufficient": False,
        "noDominantFactor": no_dominant,
        "overview": overview,
        "factors": ranked,
        "intersections": intersections(profiles, cfg),
        "slices": slices,
        "heatmap": heatmap(profiles, cfg),
        "trends": period_rates,
        "multivariate": multivariate(profiles, cfg),
        "recommendations": recommendations(ranked),
        "firstYearShare": first_year_share,
        "story": story(overview, ranked, slices),
        "unavailable": unavailable,
        "disclaimer": CAUSALITY_DISCLAIMER,
        "dataQuality": data_quality,
        "definition": {
            "dropoutStatuses": sorted(DROPOUT_STATUSES),
            "retainedStatuses": sorted(RETAINED_STATUSES),
            "note": (
                "CLASSORA has no built-in dropout field. Analysis uses explicit rows in student_academic_outcomes. "
                "DROPPED_OUT, WITHDRAWN, and DISCONTINUED count as observed dropout outcomes. "
                "Risk scores are not treated as dropouts."
            ),
        },
    }
    if no_dominant:
        payload["emptyMessage"] = "No dominant dropout-associated factor was identified in the current analysis period."
    return payload


def _factor_drill(exposed, subjects, cfg):
    if not exposed:
        return {"sections": [], "semesters": [], "courses": []}
    return slice_groups(exposed, subjects, cfg)
