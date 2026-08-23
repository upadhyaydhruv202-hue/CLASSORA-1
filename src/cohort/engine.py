"""Institutional cohort anomaly engine.

Operates on a classroom bundle assembled from existing CLASSORA tables.
Does not invent departments, years, calendars, or engagement that are not present.
Statistical detection is the source of truth — hypotheses are not confirmed causes.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone

from src.cohort import stats as S

COHORT_INSTITUTION = "INSTITUTION"
COHORT_SECTION = "SECTION"
COHORT_COURSE = "COURSE"
COHORT_SEMESTER = "SEMESTER"
COHORT_FACULTY_COURSE = "FACULTY_COURSE"

METRIC_ATTENDANCE = "ATTENDANCE"
METRIC_ASSIGNMENT = "ASSIGNMENT"
METRIC_MARKS = "MARKS"
METRIC_ENGAGEMENT = "ENGAGEMENT"
METRIC_MULTI = "MULTI"
METRIC_DATA_QUALITY = "DATA_QUALITY"

DEFAULT_CONFIG = {
    "min_cohort_size": 10,
    "min_baseline_periods": 4,
    "current_window_days": 7,
    "baseline_weeks": 6,
    "min_affected_percent": 30.0,
    "min_anomaly_score": 60.0,
    "watch_score": 30.0,
    "moderate_score": 50.0,
    "high_score": 70.0,
    "critical_score": 85.0,
    "recovery_periods": 2,
    "affected_gap_pp": 8.0,
    "volume_collapse_ratio": 0.25,
    "notify_severities": ["HIGH", "CRITICAL"],
    "pass_mark": 40.0,
}

HYPOTHESIS_DISCLAIMER = (
    "These are possible contributing factors based on statistical patterns. "
    "They are hypotheses for investigation, not confirmed causes, and they do not "
    "assign responsibility to a faculty member, department, course, student, or external event."
)


def normalize_config(raw=None):
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key not in cfg or value is None or value == "":
                continue
            if key == "notify_severities":
                items = value if isinstance(value, (list, tuple)) else str(value).split(",")
                cfg[key] = [str(item).strip().upper() for item in items if str(item).strip()]
                continue
            if key in ("min_cohort_size", "min_baseline_periods", "current_window_days", "baseline_weeks", "recovery_periods"):
                try:
                    cfg[key] = int(value)
                except (TypeError, ValueError):
                    continue
                continue
            try:
                cfg[key] = float(value)
            except (TypeError, ValueError):
                continue
    cfg["min_cohort_size"] = max(1, int(cfg["min_cohort_size"]))
    cfg["min_baseline_periods"] = max(1, int(cfg["min_baseline_periods"]))
    cfg["current_window_days"] = max(1, int(cfg["current_window_days"]))
    cfg["baseline_weeks"] = max(2, min(16, int(cfg["baseline_weeks"])))
    cfg["recovery_periods"] = max(1, int(cfg["recovery_periods"]))
    return cfg


def parse_ts(value):
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sid(row, key="student_id"):
    return _int((row or {}).get(key))


def week_windows(as_of, current_days, baseline_weeks):
    end = as_of.replace(hour=23, minute=59, second=59, microsecond=0)
    current_start = (as_of - timedelta(days=current_days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    current = (current_start, end)
    weeks = []
    cursor = current_start - timedelta(seconds=1)
    for _ in range(baseline_weeks):
        week_end = cursor.replace(hour=23, minute=59, second=59, microsecond=0)
        week_start = (week_end - timedelta(days=6)).replace(hour=0, minute=0, second=0, microsecond=0)
        weeks.append((week_start, week_end))
        cursor = week_start - timedelta(seconds=1)
    weeks.reverse()
    return current, weeks


def in_window(ts, window):
    if ts is None or not window:
        return False
    start, end = window
    return start <= ts <= end


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


def _inactive_ids(bundle):
    blocked = set()
    for row in bundle.get("moderation") or []:
        status = str(row.get("status") or "").upper()
        sid = _sid(row)
        if sid is None:
            continue
        if status in ("BANNED", "SUSPENDED"):
            blocked.add(sid)
    return blocked


def active_enrollments(bundle):
    blocked = _inactive_ids(bundle)
    subjects = _subject_map(bundle)
    rows = []
    for row in bundle.get("enrollments") or []:
        student_id = _sid(row)
        subject_id = _int(row.get("subject_id"))
        if student_id is None or subject_id is None:
            continue
        if student_id in blocked:
            continue
        if subject_id not in subjects:
            continue
        rows.append({"student_id": student_id, "subject_id": subject_id})
    return rows, subjects


def build_cohorts(bundle, config):
    enrollments, subjects = active_enrollments(bundle)
    by_course = defaultdict(set)
    by_section = defaultdict(set)
    institution = set()
    for row in enrollments:
        institution.add(row["student_id"])
        by_course[row["subject_id"]].add(row["student_id"])
        section = subjects[row["subject_id"]]["section"]
        by_section[section].add(row["student_id"])

    by_semester = defaultdict(set)
    for row in bundle.get("academic") or []:
        semester = str(row.get("semester") or "").strip()
        student_id = _sid(row)
        if not semester or student_id is None or student_id not in institution:
            continue
        by_semester[semester].add(student_id)

    cohorts = []
    inst_name = (bundle.get("institution_name") or "").strip() or "Entire institution"
    cohorts.append({
        "type": COHORT_INSTITUTION,
        "key": "institution:default",
        "label": inst_name,
        "students": institution,
        "subject_ids": set(subjects),
        "section": None,
        "subject_id": None,
        "subject_name": None,
        "subject_code": None,
        "teacher_id": None,
        "semester": None,
    })
    for section, students in sorted(by_section.items()):
        subject_ids = {sid for sid, sub in subjects.items() if sub["section"] == section}
        cohorts.append({
            "type": COHORT_SECTION,
            "key": f"section:{section}",
            "label": f"Section {section}",
            "students": students,
            "subject_ids": subject_ids,
            "section": section,
            "subject_id": None,
            "subject_name": None,
            "subject_code": None,
            "teacher_id": None,
            "semester": None,
        })
    for subject_id, students in sorted(by_course.items()):
        sub = subjects[subject_id]
        label = f"{sub['name']} — {sub['section']}"
        cohorts.append({
            "type": COHORT_COURSE,
            "key": f"course:{subject_id}",
            "label": label,
            "students": students,
            "subject_ids": {subject_id},
            "section": sub["section"],
            "subject_id": subject_id,
            "subject_name": sub["name"],
            "subject_code": sub["subject_code"],
            "teacher_id": sub["teacher_id"],
            "semester": None,
        })
    for semester, students in sorted(by_semester.items()):
        cohorts.append({
            "type": COHORT_SEMESTER,
            "key": f"semester:{semester}",
            "label": f"Semester {semester}",
            "students": students,
            "subject_ids": set(subjects),
            "section": None,
            "subject_id": None,
            "subject_name": None,
            "subject_code": None,
            "teacher_id": None,
            "semester": semester,
        })
    return cohorts, subjects


def _index_attendance(bundle):
    rows = []
    for row in bundle.get("attendance") or []:
        ts = parse_ts(row.get("timestamp"))
        student_id = _sid(row)
        subject_id = _int(row.get("subject_id"))
        if student_id is None or subject_id is None or ts is None:
            continue
        rows.append({
            "student_id": student_id,
            "subject_id": subject_id,
            "timestamp": ts,
            "is_present": bool(row.get("is_present")),
        })
    return rows


def _index_academic(bundle):
    rows = []
    for row in bundle.get("academic") or []:
        ts = parse_ts(row.get("recorded_at") or row.get("created_at"))
        student_id = _sid(row)
        if student_id is None or ts is None:
            continue
        score = S.finite(row.get("score"))
        max_score = S.finite(row.get("max_score"))
        pct = S.safe_div(100.0 * score, max_score) if score is not None and max_score else None
        rows.append({
            "student_id": student_id,
            "subject_id": _int(row.get("subject_id")),
            "semester": str(row.get("semester") or "").strip() or None,
            "timestamp": ts,
            "score": score,
            "max_score": max_score,
            "pct": pct,
            "scored": pct is not None,
            "backlog": bool(row.get("backlog")),
        })
    return rows


def _index_lms(bundle):
    rows = []
    for row in bundle.get("lms") or []:
        ts = parse_ts(row.get("occurred_at") or row.get("timestamp"))
        student_id = _sid(row)
        if student_id is None or ts is None:
            continue
        rows.append({"student_id": student_id, "timestamp": ts})
    return rows


def _attendance_slice(logs, cohort, window):
    students = cohort["students"]
    subjects = cohort["subject_ids"]
    out = []
    for row in logs:
        if row["student_id"] not in students:
            continue
        if subjects and row["subject_id"] not in subjects:
            continue
        if not in_window(row["timestamp"], window):
            continue
        out.append(row)
    return out


def _academic_slice(logs, cohort, window):
    students = cohort["students"]
    subjects = cohort["subject_ids"]
    out = []
    for row in logs:
        if row["student_id"] not in students:
            continue
        if cohort["type"] == COHORT_COURSE and row.get("subject_id") not in subjects:
            continue
        if cohort["type"] == COHORT_SECTION and row.get("subject_id") is not None and row["subject_id"] not in subjects:
            continue
        if cohort["type"] == COHORT_SEMESTER and cohort.get("semester"):
            if row.get("semester") and row.get("semester") != cohort["semester"]:
                continue
        if not in_window(row["timestamp"], window):
            continue
        out.append(row)
    return out


def attendance_rate(logs):
    if not logs:
        return None, 0, 0
    present = sum(1 for row in logs if row.get("is_present"))
    return round(100.0 * present / len(logs), 1), present, len(logs)


def assignment_metrics(logs):
    if not logs:
        return None, None, None, 0
    scored = [row for row in logs if row.get("scored")]
    completion = round(100.0 * len(scored) / len(logs), 1)
    marks = [row["pct"] for row in scored if row.get("pct") is not None]
    avg = round(S.mean(marks), 1) if marks else None
    med = round(S.median(marks), 1) if marks else None
    return completion, avg, med, len(logs)


def pass_rate(logs, pass_mark=40.0):
    scored = [row["pct"] for row in logs or [] if row.get("pct") is not None]
    if not scored:
        return None
    passed = sum(1 for pct in scored if pct >= pass_mark)
    return round(100.0 * passed / len(scored), 1)


def engagement_rate(logs, students):
    if not students:
        return None, 0
    if not logs:
        return 0.0, 0
    active = {row["student_id"] for row in logs}
    return round(100.0 * len(active) / len(students), 1), len(logs)


def _student_attendance_rates(logs, students):
    grouped = defaultdict(lambda: {"present": 0, "total": 0})
    for row in logs:
        grouped[row["student_id"]]["total"] += 1
        if row.get("is_present"):
            grouped[row["student_id"]]["present"] += 1
    rates = {}
    for sid in students:
        row = grouped.get(sid)
        if not row or row["total"] <= 0:
            rates[sid] = None
        else:
            rates[sid] = round(100.0 * row["present"] / row["total"], 1)
    return rates


def _consecutive_absence_share(logs, students):
    if not students:
        return None
    by_student = defaultdict(list)
    for row in logs:
        by_student[row["student_id"]].append(row)
    flagged = 0
    observed = 0
    for sid in students:
        series = sorted(by_student.get(sid) or [], key=lambda r: r["timestamp"])
        if not series:
            continue
        observed += 1
        streak = 0
        for row in reversed(series):
            if row.get("is_present"):
                break
            streak += 1
        if streak >= 3:
            flagged += 1
    if not observed:
        return None
    return round(100.0 * flagged / observed, 1)


def _affected_from_rates(current_rates, baseline_rates, cohort_baseline, gap, peers_have_data):
    affected = []
    threshold = None
    if cohort_baseline is not None:
        threshold = cohort_baseline - gap
    for sid, rate in current_rates.items():
        personal = baseline_rates.get(sid)
        if rate is None:
            if peers_have_data and (personal is not None or cohort_baseline is not None):
                affected.append(sid)
            continue
        flags = []
        if threshold is not None and rate <= threshold:
            flags.append(True)
        if personal is not None and rate <= personal - gap:
            flags.append(True)
        if flags:
            affected.append(sid)
    return affected


def _metric_observation(name, current, baseline_values, current_count, expected_count, cohort, config, affected_ids, extra=None):
    usable = [v for v in baseline_values if v is not None]
    baseline = S.median(usable) if usable else None
    if baseline is None:
        baseline = S.mean(usable)
    pp = S.percentage_point_change(current, baseline)
    rel = S.relative_percentage_change(current, baseline)
    z = S.z_score(current, usable)
    rz = S.robust_z_score(current, usable)
    ewma_base = S.ewma(usable)
    size = len(cohort["students"])
    affected_pct = S.affected_percentage(len(affected_ids), size)
    conf = S.confidence_from_evidence(
        baseline_periods=len(usable),
        min_periods=config["min_baseline_periods"],
        cohort_size=size,
        min_size=config["min_cohort_size"],
        record_count=current_count,
        expected_count=expected_count,
    )
    volume_ratio = S.safe_div(current_count, expected_count)
    collapsed = bool(
        expected_count is not None
        and expected_count >= 20
        and current_count < config["volume_collapse_ratio"] * expected_count
    )
    score = S.anomaly_score(
        pp_change=pp,
        robust_z=rz,
        z=z,
        affected_pct=affected_pct,
        metric_count=1,
        persistence=0,
        confidence=conf,
        rarity=min(5.0, abs(rz or z or 0) * 0.4) if (rz is not None or z is not None) else 0,
    )
    decline = pp is not None and pp < 0
    payload = {
        "metric_name": name,
        "current": S.finite(current),
        "baseline": S.finite(baseline),
        "baseline_values": [S.finite(v) for v in usable],
        "pp_change": pp,
        "rel_change": rel,
        "z": S.finite(z),
        "robust_z": S.finite(rz),
        "ewma": S.finite(ewma_base),
        "record_count": int(current_count or 0),
        "expected_count": int(expected_count) if expected_count is not None else None,
        "volume_ratio": S.finite(volume_ratio),
        "collapsed": collapsed,
        "cohort_size": size,
        "affected_ids": list(affected_ids),
        "affected_count": len(affected_ids),
        "affected_pct": affected_pct,
        "confidence": conf,
        "score": score,
        "decline": decline,
        "extra": extra or {},
    }
    return payload


def _explain_metric(obs, label):
    current = obs["current"]
    baseline = obs["baseline"]
    pp = obs["pp_change"]
    rz = obs["robust_z"]
    z = obs["z"]
    affected = obs["affected_count"]
    size = obs["cohort_size"]
    pct = obs["affected_pct"]
    parts = []
    if current is None or baseline is None:
        parts.append(f"{label} does not have a comparable current and baseline value.")
    else:
        unit = "percentage points" if obs["metric_name"] in ("attendance_rate", "assignment_completion", "engagement_rate", "pass_rate") else "points"
        direction = "declined" if (pp or 0) < 0 else "changed"
        parts.append(
            f"{label} {direction} from a historical median of {baseline} to {current} "
            f"({pp:+.1f} {unit})."
        )
    if rz is not None:
        parts.append(f"The deviation is {abs(rz):.1f} robust standard deviations from the rolling baseline.")
    elif z is not None:
        parts.append(f"The deviation is {abs(z):.1f} standard deviations from the historical mean.")
    if size:
        parts.append(f"The change affects {affected} of {size} enrolled students ({pct}%).")
    return " ".join(parts)


def _hypotheses(primary, members, all_signals, context):
    causes = []
    metric_names = {m["metric_name"] for m in members}
    att = next((m for m in members if m["metric_name"] == "attendance_rate"), None)
    assignment = next((m for m in members if m["metric_name"] == "assignment_completion"), None)
    marks = next((m for m in members if m["metric_name"] == "average_marks"), None)
    collapsed = any(m.get("collapsed") for m in members) or primary.get("metric_type") == METRIC_DATA_QUALITY

    def add(code, title, evidence_level, why):
        causes.append({
            "id": code,
            "title": title,
            "confidence": evidence_level,
            "why": why,
            "confirmed": False,
        })

    if collapsed:
        expected = primary.get("expected_count") or members[0].get("expected_count")
        current_n = primary.get("record_count") or members[0].get("record_count")
        add(
            "data_collection",
            "Possible data collection issue",
            "high" if (S.safe_div(current_n, expected) or 1) < 0.15 else "medium",
            f"Record volume fell from about {expected} to {current_n} in the current window. "
            "Missing records are not interpreted as student absenteeism.",
        )

    course_alerts = [
        s for s in all_signals
        if s.get("cohort_type") == COHORT_COURSE and s.get("decline") and (s.get("score") or 0) >= 50
    ]
    section_alerts = [
        s for s in all_signals
        if s.get("cohort_type") == COHORT_SECTION and s.get("decline") and (s.get("score") or 0) >= 50
    ]
    n_courses = max(1, context.get("n_courses") or 1)
    n_sections = max(1, context.get("n_sections") or 1)

    if primary.get("cohort_type") == COHORT_COURSE:
        siblings = [s for s in course_alerts if s.get("subject_id") != primary.get("subject_id")]
        quiet = [s for s in siblings if abs(s.get("pp_change") or 0) < 5]
        if n_courses >= 2 and (not siblings or len(quiet) >= max(1, len(siblings) - 0)):
            add(
                "course_specific",
                "Course-specific pattern",
                "high" if len(course_alerts) <= 1 else "medium",
                "The unusual change is concentrated in this course while other courses remained near their historical baseline.",
            )
        teacher_courses = [
            s for s in course_alerts
            if s.get("teacher_id") and s.get("teacher_id") == primary.get("teacher_id")
        ]
        other_teacher = [s for s in course_alerts if s.get("teacher_id") != primary.get("teacher_id")]
        if primary.get("teacher_id") and teacher_courses and len(other_teacher) == 0 and n_courses >= 2:
            add(
                "faculty_course",
                "Course/faculty-associated pattern detected — administrative review recommended",
                "medium",
                "The decline is concentrated within courses associated with this faculty-course grouping. "
                "This is a concentration pattern, not a finding that a faculty member caused the change.",
            )

    if primary.get("cohort_type") == COHORT_SECTION or (len(section_alerts) == 1 and primary.get("section")):
        add(
            "section_pattern",
            "Section-level pattern",
            "medium",
            "The unusual change is associated with one section more than with the rest of the institution.",
        )

    if primary.get("cohort_type") == COHORT_SEMESTER:
        add(
            "semester_pattern",
            "Semester-wide pattern",
            "medium",
            "Students sharing this semester label moved together, which is a cohort-level pattern requiring investigation.",
        )

    if primary.get("cohort_type") == COHORT_INSTITUTION or len(section_alerts) >= max(2, 0.5 * n_sections):
        add(
            "institution_event",
            "Institution-wide event or scheduling pattern",
            "medium" if len(section_alerts) >= 2 else "low",
            "Several organizational groups changed in the same direction at the same time. "
            "A shared schedule, calendar, or data-collection factor may require investigation.",
        )
        add(
            "external_schedule",
            "External or scheduling-related factor may require investigation",
            "low",
            "CLASSORA has no academic calendar, holiday, or exam-schedule records to test this hypothesis. "
            "The simultaneous timing is the only supporting signal.",
        )

    if att and assignment and att.get("decline") and assignment.get("decline"):
        add(
            "engagement_workload",
            "Engagement/workload-related pattern",
            "medium",
            "Attendance and assignment completion declined together, which is consistent with a workload or engagement shift — not a confirmed cause.",
        )
    elif att and att.get("decline") and (not assignment or not assignment.get("decline")) and (not marks or not marks.get("decline")):
        add(
            "attendance_specific",
            "Attendance-specific issue or attendance recording anomaly",
            "medium",
            "Attendance moved unusually while marks and assignment completion stayed nearer to baseline.",
        )
    if marks and marks.get("decline") and (not att or abs(att.get("pp_change") or 0) < 4):
        add(
            "assessment_shift",
            "Assessment difficulty or academic performance shift",
            "medium",
            "Average marks declined while attendance remained comparatively stable. This may reflect an assessment or scoring pattern.",
        )
    if assignment and assignment.get("decline"):
        add(
            "assignment_workload",
            "Assignment workload pattern",
            "low" if "engagement_workload" in {c["id"] for c in causes} else "medium",
            "Assignment completion moved away from its historical baseline during the current window.",
        )

    add(
        "external_event",
        "External event",
        "insufficient",
        "No institutional calendar, holiday, or exam schedule is stored in CLASSORA, so an external event cannot be evidenced.",
    )

    # Keep unique ids, strongest first.
    rank = {"high": 0, "medium": 1, "low": 2, "insufficient": 3}
    uniq = []
    seen = set()
    for item in sorted(causes, key=lambda c: rank.get(c["confidence"], 9)):
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        uniq.append(item)
    return uniq


def _should_alert(obs, config, force_data_quality=False):
    if force_data_quality or obs.get("collapsed"):
        return True
    if obs.get("current") is None or obs.get("baseline") is None:
        return False
    if not obs.get("decline"):
        return False
    if obs["cohort_size"] < config["min_cohort_size"]:
        return False
    if len(obs.get("baseline_values") or []) < config["min_baseline_periods"]:
        return False
    if (obs.get("affected_pct") or 0) < config["min_affected_percent"]:
        return False
    return (obs.get("score") or 0) >= config["min_anomaly_score"]


def _signal_from_obs(cohort, metric_type, obs, config, extra_metrics=None):
    members = [obs] + list(extra_metrics or [])
    metric_count = len({m["metric_name"] for m in members})
    combined_score = S.anomaly_score(
        pp_change=max((abs(m.get("pp_change") or 0) for m in members), default=0) * (-1 if any(m.get("decline") for m in members) else 1),
        robust_z=min((m.get("robust_z") for m in members if m.get("robust_z") is not None), default=None),
        z=min((m.get("z") for m in members if m.get("z") is not None), default=None),
        affected_pct=max((m.get("affected_pct") or 0 for m in members), default=0),
        metric_count=metric_count,
        persistence=0,
        confidence=S.mean([m.get("confidence") for m in members]) or obs.get("confidence"),
    )
    if metric_type == METRIC_DATA_QUALITY:
        combined_score = max(combined_score, 62.0)
        severity = S.classify_severity(combined_score, config)
        if severity == "NORMAL":
            severity = "MODERATE"
    else:
        severity = S.classify_severity(combined_score, config)
    identity = f"{cohort['key']}|{metric_type}"
    explanation = _explain_metric(obs, _metric_label(obs["metric_name"]))
    if metric_count > 1:
        explanation = (
            "Multiple academic indicators have shifted significantly from historical baseline. "
            + explanation
        )
    return {
        "cohort_type": cohort["type"],
        "cohort_key": cohort["key"],
        "cohort_label": cohort["label"],
        "section": cohort.get("section"),
        "subject_id": cohort.get("subject_id"),
        "subject_name": cohort.get("subject_name"),
        "subject_code": cohort.get("subject_code"),
        "teacher_id": cohort.get("teacher_id"),
        "semester": cohort.get("semester"),
        "metric_type": metric_type,
        "metric_name": obs["metric_name"] if metric_count == 1 else "multi_metric",
        "identity_key": identity,
        "current": obs["current"],
        "baseline": obs["baseline"],
        "pp_change": obs["pp_change"],
        "rel_change": obs["rel_change"],
        "z": obs["z"],
        "robust_z": obs["robust_z"],
        "score": combined_score,
        "severity": severity,
        "confidence": S.finite(S.mean([m.get("confidence") for m in members]) or obs.get("confidence")),
        "cohort_size": obs["cohort_size"],
        "affected_count": max(m["affected_count"] for m in members),
        "affected_pct": max(m["affected_pct"] for m in members),
        "affected_ids": sorted({sid for m in members for sid in m.get("affected_ids") or []}),
        "record_count": obs["record_count"],
        "expected_count": obs["expected_count"],
        "collapsed": any(m.get("collapsed") for m in members),
        "decline": any(m.get("decline") for m in members),
        "explanation": explanation,
        "members": members,
        "window": None,
        "baseline_span": None,
    }


def _metric_label(name):
    return {
        "attendance_rate": "Attendance",
        "assignment_completion": "Assignment completion",
        "average_marks": "Average marks",
        "engagement_rate": "Platform activity",
        "pass_rate": "Pass rate",
        "multi_metric": "Multiple metrics",
        "record_volume": "Data volume",
    }.get(name, name.replace("_", " ").title())


def _observe_attendance(cohort, att_logs, current, weeks, config):
    current_logs = _attendance_slice(att_logs, cohort, current)
    week_rates = []
    week_counts = []
    for window in weeks:
        logs = _attendance_slice(att_logs, cohort, window)
        rate, _present, total = attendance_rate(logs)
        if total:
            week_rates.append(rate)
            week_counts.append(total)
        else:
            week_rates.append(None)
            week_counts.append(0)
    current_rate, _p, current_n = attendance_rate(current_logs)
    expected = S.median([c for c in week_counts if c]) 
    baseline_logs = []
    for window in weeks:
        baseline_logs.extend(_attendance_slice(att_logs, cohort, window))
    current_rates = _student_attendance_rates(current_logs, cohort["students"])
    baseline_rates = _student_attendance_rates(baseline_logs, cohort["students"])
    peers = current_n > 0
    baseline_med = S.median([v for v in week_rates if v is not None])
    affected = _affected_from_rates(current_rates, baseline_rates, baseline_med, config["affected_gap_pp"], peers)
    extra = {"consecutive_absence_share": _consecutive_absence_share(current_logs, cohort["students"])}
    obs = _metric_observation(
        "attendance_rate", current_rate, week_rates, current_n, expected, cohort, config, affected, extra
    )
    snapshots = _snapshots(cohort, "attendance_rate", weeks, week_rates, week_counts, current, current_rate, current_n, expected)
    return obs, snapshots


def _observe_academic(cohort, aca_logs, current, weeks, config):
    snapshots = []
    observations = []
    week_completion = []
    week_marks = []
    week_counts = []
    for window in weeks:
        logs = _academic_slice(aca_logs, cohort, window)
        completion, avg, _med, total = assignment_metrics(logs)
        week_completion.append(completion)
        week_marks.append(avg)
        week_counts.append(total)
    current_logs = _academic_slice(aca_logs, cohort, current)
    completion, avg, median_marks, current_n = assignment_metrics(current_logs)
    expected = S.median([c for c in week_counts if c])
    baseline_logs = []
    for window in weeks:
        baseline_logs.extend(_academic_slice(aca_logs, cohort, window))

    if any(v is not None for v in week_completion) or completion is not None:
        current_by = defaultdict(lambda: {"scored": 0, "total": 0})
        base_by = defaultdict(lambda: {"scored": 0, "total": 0})
        for row in current_logs:
            current_by[row["student_id"]]["total"] += 1
            if row.get("scored"):
                current_by[row["student_id"]]["scored"] += 1
        for row in baseline_logs:
            base_by[row["student_id"]]["total"] += 1
            if row.get("scored"):
                base_by[row["student_id"]]["scored"] += 1
        affected = []
        base_comp = S.median([v for v in week_completion if v is not None])
        for sid in cohort["students"]:
            cur = current_by.get(sid)
            if current_n <= 0:
                break
            if not cur or cur["total"] == 0:
                if current_n > 0:
                    affected.append(sid)
                continue
            rate = 100.0 * cur["scored"] / cur["total"]
            if base_comp is not None and rate <= base_comp - config["affected_gap_pp"]:
                affected.append(sid)
        obs = _metric_observation(
            "assignment_completion", completion, week_completion, current_n, expected, cohort, config, affected
        )
        observations.append(obs)
        snapshots.extend(_snapshots(cohort, "assignment_completion", weeks, week_completion, week_counts, current, completion, current_n, expected))

    if any(v is not None for v in week_marks) or avg is not None:
        current_marks = defaultdict(list)
        base_marks = defaultdict(list)
        for row in current_logs:
            if row.get("pct") is not None:
                current_marks[row["student_id"]].append(row["pct"])
        for row in baseline_logs:
            if row.get("pct") is not None:
                base_marks[row["student_id"]].append(row["pct"])
        base_avg = S.median([v for v in week_marks if v is not None])
        affected = []
        for sid, values in current_marks.items():
            cur = S.mean(values)
            personal = S.mean(base_marks.get(sid) or [])
            if cur is None:
                continue
            if base_avg is not None and cur <= base_avg - max(5.0, config["affected_gap_pp"] * 0.6):
                affected.append(sid)
            elif personal is not None and cur <= personal - 5:
                affected.append(sid)
        extra = {
            "median_marks": median_marks,
            "pass_rate": pass_rate(current_logs, config["pass_mark"]),
            "baseline_pass_rate": pass_rate(baseline_logs, config["pass_mark"]),
        }
        obs = _metric_observation(
            "average_marks", avg, week_marks, len([r for r in current_logs if r.get("scored")]), expected, cohort, config, affected, extra
        )
        observations.append(obs)
        snapshots.extend(_snapshots(cohort, "average_marks", weeks, week_marks, week_counts, current, avg, current_n, expected))
    return observations, snapshots


def _observe_engagement(cohort, lms_logs, current, weeks, config):
    if not lms_logs:
        return None, []
    week_rates = []
    week_counts = []
    for window in weeks:
        logs = [row for row in lms_logs if row["student_id"] in cohort["students"] and in_window(row["timestamp"], window)]
        rate, total = engagement_rate(logs, cohort["students"])
        week_rates.append(rate if total else None)
        week_counts.append(total)
    if not any(v is not None for v in week_rates):
        return None, []
    current_logs = [row for row in lms_logs if row["student_id"] in cohort["students"] and in_window(row["timestamp"], current)]
    rate, current_n = engagement_rate(current_logs, cohort["students"])
    expected = S.median([c for c in week_counts if c])
    active = {row["student_id"] for row in current_logs}
    affected = [sid for sid in cohort["students"] if sid not in active]
    obs = _metric_observation("engagement_rate", rate, week_rates, current_n, expected, cohort, config, affected)
    snaps = _snapshots(cohort, "engagement_rate", weeks, week_rates, week_counts, current, rate, current_n, expected)
    return obs, snaps


def _snapshots(cohort, metric_name, weeks, values, counts, current, current_value, current_n, expected):
    rows = []
    for window, value, count in zip(weeks, values, counts):
        rows.append({
            "cohort_key": cohort["key"],
            "metric_name": metric_name,
            "period_start": _iso(window[0]),
            "period_end": _iso(window[1]),
            "period_kind": "WEEK",
            "value": S.finite(value),
            "record_count": int(count or 0),
            "expected_count": int(expected) if expected is not None else None,
            "cohort_size": len(cohort["students"]),
        })
    rows.append({
        "cohort_key": cohort["key"],
        "metric_name": metric_name,
        "period_start": _iso(current[0]),
        "period_end": _iso(current[1]),
        "period_kind": "CURRENT",
        "value": S.finite(current_value),
        "record_count": int(current_n or 0),
        "expected_count": int(expected) if expected is not None else None,
        "cohort_size": len(cohort["students"]),
    })
    return rows


def _comparisons(primary, all_obs, institution_obs):
    out = {"institution": None, "siblings": []}
    if institution_obs:
        out["institution"] = {
            "label": "Institution",
            "current": institution_obs.get("current"),
            "baseline": institution_obs.get("baseline"),
        }
    if primary.get("cohort_type") == COHORT_COURSE:
        for item in all_obs:
            if item.get("cohort_type") != COHORT_COURSE:
                continue
            if item.get("metric_name") != primary.get("metric_name") and item.get("metric_type") != primary.get("metric_type"):
                if item.get("metric_name") != (primary.get("members") or [{}])[0].get("metric_name"):
                    continue
            if item.get("cohort_key") == primary.get("cohort_key"):
                continue
            out["siblings"].append({
                "label": item.get("cohort_label"),
                "current": item.get("current"),
                "baseline": item.get("baseline"),
                "ppChange": item.get("pp_change"),
            })
    elif primary.get("cohort_type") == COHORT_SECTION:
        for item in all_obs:
            if item.get("cohort_type") != COHORT_SECTION or item.get("cohort_key") == primary.get("cohort_key"):
                continue
            if item.get("metric_name") not in (primary.get("metric_name"), "attendance_rate", "multi_metric"):
                continue
            out["siblings"].append({
                "label": item.get("cohort_label"),
                "current": item.get("current"),
                "baseline": item.get("baseline"),
                "ppChange": item.get("pp_change"),
            })
    out["siblings"] = out["siblings"][:8]
    return out


def _group_alerts(alerts, context, all_signals, config, watches=None):
    if not alerts and not watches:
        return []
    by_cohort = defaultdict(list)
    seed = list(watches or alerts or [])
    if alerts:
        seen = {(item.get("identity_key"), item.get("metric_type")) for item in seed}
        for item in alerts:
            key = (item.get("identity_key"), item.get("metric_type"))
            if key not in seen:
                seed.append(item)
                seen.add(key)
    for item in seed:
        by_cohort[item["cohort_key"]].append(item)

    merged = []
    for _key, items in by_cohort.items():
        dq = [i for i in items if i["metric_type"] == METRIC_DATA_QUALITY or i.get("collapsed")]
        academic = [i for i in items if i not in dq]
        if dq:
            lead = dq[0]
            extra = [m for row in dq for m in row.get("members") or []]
            lead = dict(lead)
            lead["members"] = extra or lead.get("members")
            lead["metric_type"] = METRIC_DATA_QUALITY
            lead["identity_key"] = f"{lead['cohort_key']}|{METRIC_DATA_QUALITY}"
            merged.append(lead)
        if len(academic) >= 2:
            lead = dict(academic[0])
            members = [m for row in academic for m in row.get("members") or []]
            lead["members"] = members
            lead["metric_type"] = METRIC_MULTI
            lead["metric_name"] = "multi_metric"
            lead["identity_key"] = f"{lead['cohort_key']}|{METRIC_MULTI}"
            lead["score"] = S.anomaly_score(
                pp_change=min((row.get("pp_change") or 0) for row in academic),
                robust_z=min((row.get("robust_z") for row in academic if row.get("robust_z") is not None), default=None),
                z=min((row.get("z") for row in academic if row.get("z") is not None), default=None),
                affected_pct=max(row.get("affected_pct") or 0 for row in academic),
                metric_count=len(academic),
                confidence=S.mean([row.get("confidence") for row in academic]),
            )
            lead["severity"] = S.classify_severity(lead["score"], config)
            lead["explanation"] = (
                "Multiple academic indicators have shifted significantly from historical baseline. "
                + (academic[0].get("explanation") or "")
            )
            lead["affected_count"] = max(row.get("affected_count") or 0 for row in academic)
            lead["affected_pct"] = max(row.get("affected_pct") or 0 for row in academic)
            lead["affected_ids"] = sorted({sid for row in academic for sid in row.get("affected_ids") or []})
            merged.append(lead)
        elif len(academic) == 1:
            if (academic[0].get("score") or 0) >= config["min_anomaly_score"] or academic[0].get("collapsed"):
                merged.append(academic[0])

    merged = [
        item for item in merged
        if item.get("collapsed")
        or item.get("metric_type") == METRIC_DATA_QUALITY
        or (item.get("score") or 0) >= config["min_anomaly_score"]
    ]

    courses = [m for m in merged if m["cohort_type"] == COHORT_COURSE]
    sections = [m for m in merged if m["cohort_type"] == COHORT_SECTION]
    institutions = [m for m in merged if m["cohort_type"] == COHORT_INSTITUTION]
    semesters = [m for m in merged if m["cohort_type"] == COHORT_SEMESTER]
    n_sections = context.get("n_sections") or 0
    n_courses = context.get("n_courses") or 0

    suppressed = set()
    primaries = []

    def attach_children(parent, children):
        parent = dict(parent)
        parent["children"] = [
            {
                "cohortType": c["cohort_type"],
                "cohortKey": c["cohort_key"],
                "label": c["cohort_label"],
                "metric": c["metric_type"],
                "score": c["score"],
                "severity": c["severity"],
                "current": c["current"],
                "baseline": c["baseline"],
                "ppChange": c["pp_change"],
                "affectedPct": c["affected_pct"],
            }
            for c in children
        ]
        parent["is_primary"] = True
        return parent

    wide_sections = [
        s for s in sections
        if s.get("decline") or s.get("metric_type") == METRIC_DATA_QUALITY
    ]
    institution_wide = bool(institutions) and n_sections >= 2 and len(wide_sections) >= max(2, int(0.5 * n_sections + 0.999))

    if institution_wide:
        parent = attach_children(institutions[0], wide_sections + courses)
        primaries.append(parent)
        suppressed.update(id(x) for x in institutions + wide_sections + courses)
    else:
        suppressed.update(id(x) for x in institutions)

    for section in sections:
        if id(section) in suppressed:
            continue
        kids = [c for c in courses if c.get("section") == section.get("section")]
        if kids and len(kids) >= max(2, int(0.5 * max(1, sum(1 for c in courses if c.get("section") == section.get("section"))) + 0.5)):
            primaries.append(attach_children(section, kids))
            suppressed.add(id(section))
            suppressed.update(id(c) for c in kids)
        elif kids and len(kids) == 1:
            suppressed.add(id(section))
        else:
            primaries.append(attach_children(section, kids))
            suppressed.add(id(section))
            suppressed.update(id(c) for c in kids)

    for semester in semesters:
        if id(semester) in suppressed:
            continue
        if len(courses) <= 1:
            suppressed.add(id(semester))
            continue
        primaries.append(attach_children(semester, courses))
        suppressed.add(id(semester))
        suppressed.update(id(c) for c in courses)

    for course in courses:
        if id(course) in suppressed:
            continue
        primaries.append(attach_children(course, []))

    for item in primaries:
        item["possible_causes"] = _hypotheses(item, item.get("members") or [], all_signals, context)
        item["comparisons"] = _comparisons(item, all_signals, context.get("institution_attendance"))
        item["disclaimer"] = HYPOTHESIS_DISCLAIMER
    return primaries


def analyze(bundle, config=None, as_of=None):
    cfg = normalize_config(config)
    now = parse_ts(as_of) or utc_now()
    current, weeks = week_windows(now, cfg["current_window_days"], cfg["baseline_weeks"])
    cohorts, _subjects = build_cohorts(bundle, cfg)
    att_logs = _index_attendance(bundle)
    aca_logs = _index_academic(bundle)
    lms_logs = _index_lms(bundle)
    has_lms = bool(lms_logs)

    snapshots = []
    skipped = []
    signals = []
    sized_sections = 0
    sized_courses = 0
    sized_semesters = 0
    history_ok_any = False
    institution_attendance = None

    for cohort in cohorts:
        size = len(cohort["students"])
        if size < cfg["min_cohort_size"]:
            skipped.append({
                "cohortKey": cohort["key"],
                "label": cohort["label"],
                "reason": "insufficient_sample",
                "cohortSize": size,
                "detail": "Insufficient sample size",
            })
            continue
        if cohort["type"] == COHORT_SECTION:
            sized_sections += 1
        elif cohort["type"] == COHORT_COURSE:
            sized_courses += 1
        elif cohort["type"] == COHORT_SEMESTER:
            sized_semesters += 1

        att_obs, att_snaps = _observe_attendance(cohort, att_logs, current, weeks, cfg)
        snapshots.extend(att_snaps)
        aca_obs, aca_snaps = _observe_academic(cohort, aca_logs, current, weeks, cfg)
        snapshots.extend(aca_snaps)
        eng_obs, eng_snaps = (None, [])
        if has_lms:
            eng_obs, eng_snaps = _observe_engagement(cohort, lms_logs, current, weeks, cfg)
            snapshots.extend(eng_snaps)

        observations = [att_obs] + aca_obs + ([eng_obs] if eng_obs else [])
        for obs in observations:
            history = len(obs.get("baseline_values") or [])
            if history >= cfg["min_baseline_periods"]:
                history_ok_any = True
            metric_type = {
                "attendance_rate": METRIC_ATTENDANCE,
                "assignment_completion": METRIC_ASSIGNMENT,
                "average_marks": METRIC_MARKS,
                "engagement_rate": METRIC_ENGAGEMENT,
            }[obs["metric_name"]]
            if obs.get("collapsed"):
                signal = _signal_from_obs(cohort, METRIC_DATA_QUALITY, obs, cfg)
                signal["window"] = current
                signal["baseline_span"] = (weeks[0][0], weeks[-1][1]) if weeks else None
                signals.append(signal)
                continue
            if history < cfg["min_baseline_periods"]:
                skipped.append({
                    "cohortKey": cohort["key"],
                    "label": cohort["label"],
                    "reason": "insufficient_history",
                    "metric": obs["metric_name"],
                    "detail": "Insufficient historical data for reliable anomaly detection.",
                    "baselinePeriods": history,
                })
                continue
            if obs.get("current") is None:
                skipped.append({
                    "cohortKey": cohort["key"],
                    "label": cohort["label"],
                    "reason": "no_data",
                    "metric": obs["metric_name"],
                    "detail": "No current-window records for this metric.",
                })
                continue
            signal = _signal_from_obs(cohort, metric_type, obs, cfg)
            signal["window"] = current
            signal["baseline_span"] = (weeks[0][0], weeks[-1][1]) if weeks else None
            signals.append(signal)
            if cohort["type"] == COHORT_INSTITUTION and obs["metric_name"] == "attendance_rate":
                institution_attendance = signal

    alerts = []
    watches = []
    for signal in signals:
        force_dq = signal["metric_type"] == METRIC_DATA_QUALITY
        lead = (signal.get("members") or [signal])[0]
        if force_dq or lead.get("collapsed"):
            alerts.append(signal)
            watches.append(signal)
            continue
        if signal.get("decline") and (signal.get("score") or 0) >= cfg.get("watch_score", 30):
            watches.append(signal)
        if _should_alert(lead, cfg):
            alerts.append(signal)

    context = {
        "n_sections": sized_sections,
        "n_courses": sized_courses,
        "n_semesters": sized_semesters,
        "institution_attendance": institution_attendance,
    }
    events = _group_alerts(alerts, context, signals, cfg, watches=watches)
    for event in events:
        event["window"] = current
        event["baseline_span"] = (weeks[0][0], weeks[-1][1]) if weeks else None
        event["window_start"] = _iso(current[0])
        event["window_end"] = _iso(current[1])
        event["baseline_start"] = _iso(weeks[0][0]) if weeks else None
        event["baseline_end"] = _iso(weeks[-1][1]) if weeks else None

    return {
        "as_of": _iso(now),
        "config": cfg,
        "cold_start": not history_ok_any,
        "insufficient_history": not history_ok_any,
        "cohorts_analyzed": sum(1 for c in cohorts if len(c["students"]) >= cfg["min_cohort_size"]),
        "cohorts_total": len(cohorts),
        "signals": signals,
        "events": events,
        "snapshots": snapshots,
        "skipped": skipped,
        "dimensions": {
            "institution": True,
            "section": sized_sections > 0,
            "course": sized_courses > 0,
            "semester": sized_semesters > 0,
            "facultyCourse": any(
                c.get("teacher_id") and len(c["students"]) >= cfg["min_cohort_size"]
                for c in cohorts if c["type"] == COHORT_COURSE
            ),
            "department": False,
            "year": False,
            "calendar": False,
        },
        "window": {"start": _iso(current[0]), "end": _iso(current[1])},
        "disclaimer": HYPOTHESIS_DISCLAIMER,
    }
