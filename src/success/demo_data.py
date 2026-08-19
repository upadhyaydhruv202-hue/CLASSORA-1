"""Clearly fictional SIH demo data. Never mixed into production writes."""

from datetime import datetime, timedelta

DEMO_BADGE = "DEMO MODE — synthetic data"

SCENARIOS = {
    "stable": "Stable Student",
    "rising": "Rising-Risk",
    "attendance": "Attendance Decline",
    "academic": "Academic Decline",
    "engagement": "Engagement Decline",
    "multiple": "Multiple-Risk",
    "success": "Successful Intervention",
    "failed": "Failed Intervention",
    "no_response": "No-Response",
    "override": "Human-Override",
    "missing": "Missing-Data",
    "low_conf": "Low-Confidence",
    "recovery": "Recovery",
}


def demo_students(scenario="multiple"):
    now = datetime.now()
    base = [
        {"student_id": -101, "name": "Asha Demo", "scenario": "stable"},
        {"student_id": -102, "name": "Rahul Demo", "scenario": "attendance"},
        {"student_id": -103, "name": "Meera Demo", "scenario": "academic"},
        {"student_id": -104, "name": "Irfan Demo", "scenario": "engagement"},
        {"student_id": -105, "name": "Priya Demo", "scenario": "multiple"},
        {"student_id": -106, "name": "Kabir Demo", "scenario": "recovery"},
    ]
    logs = []
    academic = []
    lms = []
    for s in base:
        sid = s["student_id"]
        for i in range(12):
            day = now - timedelta(days=12 - i)
            present = True
            if s["scenario"] in ("attendance", "multiple", "rising") and i > 6:
                present = i % 3 != 0
            if s["scenario"] == "stable":
                present = i != 2
            logs.append({"student_id": sid, "timestamp": day.isoformat(), "is_present": present, "subjects": {"name": "TOC", "section": "E"}})
        if s["scenario"] in ("academic", "multiple"):
            academic.append({"student_id": sid, "score": 32, "max_score": 100, "gpa": 4.2, "backlog": True, "assessment": "Midterm"})
        if s["scenario"] in ("engagement", "multiple"):
            lms.append({"student_id": sid, "event_type": "login", "occurred_at": (now - timedelta(days=20)).isoformat()})
        else:
            lms.append({"student_id": sid, "event_type": "login", "occurred_at": (now - timedelta(days=1)).isoformat()})
    cases = [
        {"id": 1, "case_code": "CASE-DEMO-1", "student_id": -105, "owner": "Counsellor Demo", "priority": "critical", "status": "open", "intervention_name": "Attendance check-in", "deadline": (now - timedelta(days=1)).isoformat(), "notes": "DEMO"},
        {"id": 2, "case_code": "CASE-DEMO-2", "student_id": -106, "owner": "Counsellor Demo", "priority": "medium", "status": "closed", "intervention_name": "Mentor weekly meeting", "deadline": (now + timedelta(days=3)).isoformat(), "notes": "DEMO recovered"},
    ]
    recs = [
        {"id": 1, "student_id": -105, "recommendation": "Attendance check-in", "reason": "Associated with attendance decline", "confidence": 0.78, "status": "pending"},
        {"id": 2, "student_id": -102, "recommendation": "Attendance check-in", "reason": "Consecutive absences", "confidence": 0.7, "status": "pending"},
    ]
    if scenario == "override":
        recs[0]["status"] = "rejected"
    if scenario == "success":
        cases[0]["status"] = "closed"
    return {
        "students": base,
        "logs": logs,
        "academic": academic,
        "lms": lms,
        "cases": cases,
        "recommendations": recs,
        "scenario": scenario,
        "scenario_label": SCENARIOS.get(scenario, scenario),
    }
