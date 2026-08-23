"""Institutional cohort anomaly detection: statistics, engine, lifecycle, API."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import _modules, router
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.cohort import engine
from src.cohort import service as cohort
from src.cohort import stats as S


AS_OF = datetime(2026, 8, 23, 12, 0, 0)


class MemoryStore:
    def __init__(self):
        self.tables = {}
        self.seq = {}

    def available(self, table):
        return True

    def last_error(self, table):
        return ""

    def insert(self, table, row):
        rows = self.tables.setdefault(table, [])
        payload = dict(row)
        payload.setdefault("id", self.seq.get(table, 1))
        self.seq[table] = int(payload["id"]) + 1
        rows.append(payload)
        return [payload]

    def select(self, table, **eq):
        rows = list(self.tables.get(table) or [])
        if not eq:
            return rows
        return [row for row in rows if all(row.get(key) == value for key, value in eq.items())]

    def update(self, table, match, values):
        changed = []
        for row in self.tables.setdefault(table, []):
            if all(row.get(key) == value for key, value in match.items()):
                row.update(values)
                changed.append(row)
        return changed

    def delete(self, table, **eq):
        kept, removed = [], []
        for row in self.tables.get(table) or []:
            if all(row.get(key) == value for key, value in eq.items()):
                removed.append(row)
            else:
                kept.append(row)
        self.tables[table] = kept
        return removed


def _bearer(role, **kwargs):
    if role == "student":
        session = session_payload(role="student", student={"student_id": kwargs.get("student_id", 1), "name": "Ada"})
    elif role == "teacher":
        session = session_payload(role="teacher", teacher={"teacher_id": kwargs.get("teacher_id", 1), "username": "tea"})
    else:
        session = session_payload(
            role=role,
            staff={"staff_id": kwargs.get("staff_id", 1), "username": "staff", "name": "Staff", "role": role},
        )
    return {"Authorization": f"Bearer {encode_token(session)}"}, session


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _windows():
    return engine.week_windows(AS_OF, 7, 6)


def _ts(window, day=0, hour=10):
    start, end = window
    stamp = start + timedelta(days=day, hours=hour)
    if stamp > end:
        stamp = end - timedelta(minutes=5)
    return stamp.isoformat()


def _subject(sid, name, section, teacher_id=1):
    return {"subject_id": sid, "name": name, "subject_code": name[:4].upper(), "section": section, "teacher_id": teacher_id}


def _enroll(students, subject_id):
    return [{"student_id": sid, "subject_id": subject_id} for sid in students]


def _sessions(students, subject_id, window, present_fn, count=3):
    logs = []
    for index in range(count):
        stamp = _ts(window, day=index)
        for sid in students:
            logs.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": stamp,
                "is_present": bool(present_fn(sid, index)),
            })
    return logs


def _academic(students, subject_id, window, scored, mark, semester="4"):
    rows = []
    stamp = _ts(window, day=2, hour=14)
    for sid in students:
        row = {
            "student_id": sid,
            "subject_id": subject_id,
            "semester": semester,
            "assessment": "quiz",
            "recorded_at": stamp,
        }
        if sid in scored:
            row["score"] = mark
            row["max_score"] = 100
        rows.append(row)
    return rows


def high_severity_bundle():
    current, weeks = _windows()
    students = list(range(1, 111))
    subjects = [_subject(1, "Operating Systems", "IT")]
    enrollments = _enroll(students, 1)
    logs = []
    academic = []
    for window in weeks:
        logs += _sessions(students, 1, window, lambda sid, session: (sid + session) % 100 < 87)
        academic += _academic(students, 1, window, set(range(1, 99)), 76)
    logs += _sessions(students, 1, current, lambda sid, session: (
        (sid <= 20 and session == 0)
        or (21 <= sid <= 82 and session <= 1)
        or sid >= 83
    ))
    academic += _academic(students, 1, current, set(range(1, 70)), 67)
    return {
        "students": [{"student_id": sid, "name": f"S{sid}"} for sid in students],
        "subjects": subjects,
        "enrollments": enrollments,
        "attendance": logs,
        "academic": academic,
        "lms": [],
        "moderation": [],
        "institution_name": "CLASSORA Demo University",
    }


def stable_bundle():
    current, weeks = _windows()
    students = list(range(1, 41))
    logs = []
    for window in weeks:
        logs += _sessions(students, 1, window, lambda sid, session: (sid + session) % 100 < 87)
    logs += _sessions(students, 1, current, lambda sid, session: (sid + session) % 100 < 86)
    return {
        "students": [{"student_id": sid, "name": f"S{sid}"} for sid in students],
        "subjects": [_subject(1, "DSA", "IT")],
        "enrollments": _enroll(students, 1),
        "attendance": logs,
        "academic": [],
        "lms": [],
        "moderation": [],
        "institution_name": "CLASSORA Demo University",
    }


def institution_wide_bundle():
    current, weeks = _windows()
    sections = [("IT-A", 1), ("CSE-A", 2), ("ECE-A", 3), ("ME-A", 4)]
    subjects = []
    enrollments = []
    logs = []
    students = []
    sid = 1
    groups = []
    for section, subject_id in sections:
        group = list(range(sid, sid + 20))
        sid += 20
        groups.append(group)
        students += group
        subjects.append(_subject(subject_id, f"Core {section}", section, teacher_id=subject_id))
        enrollments += _enroll(group, subject_id)
        for window in weeks:
            logs += _sessions(group, subject_id, window, lambda _s, session: session < 2 or (_s % 10) != 0, count=3)
        logs += _sessions(group, subject_id, current, lambda _s, session: session == 0, count=3)
    return {
        "students": [{"student_id": n, "name": f"S{n}"} for n in students],
        "subjects": subjects,
        "enrollments": enrollments,
        "attendance": logs,
        "academic": [],
        "lms": [],
        "moderation": [],
        "institution_name": "CLASSORA Demo University",
    }


def course_specific_bundle():
    current, weeks = _windows()
    students = list(range(1, 41))
    names = [(1, "Operating Systems"), (2, "DBMS"), (3, "DSA"), (4, "Java")]
    subjects = [_subject(sid, name, "IT") for sid, name in names]
    enrollments = []
    logs = []
    for sid, _name in names:
        enrollments += _enroll(students, sid)
        for window in weeks:
            logs += _sessions(students, sid, window, lambda student, session: (student + session) % 100 < 88)
        if sid == 1:
            logs += _sessions(students, sid, current, lambda student, session: session == 0)
        else:
            logs += _sessions(students, sid, current, lambda student, session: (student + session) % 100 < 88)
    return {
        "students": [{"student_id": n, "name": f"S{n}"} for n in students],
        "subjects": subjects,
        "enrollments": enrollments,
        "attendance": logs,
        "academic": [],
        "lms": [],
        "moderation": [],
        "institution_name": "CLASSORA Demo University",
    }


def data_failure_bundle():
    current, weeks = _windows()
    students = list(range(1, 51))
    logs = []
    for window in weeks:
        logs += _sessions(students, 1, window, lambda sid, session: True, count=20)
    logs += _sessions(students[:10], 1, current, lambda sid, session: sid % 2 == 0, count=3)
    return {
        "students": [{"student_id": n, "name": f"S{n}"} for n in students],
        "subjects": [_subject(1, "Networks", "IT")],
        "enrollments": _enroll(students, 1),
        "attendance": logs,
        "academic": [],
        "lms": [],
        "moderation": [],
        "institution_name": "CLASSORA Demo University",
    }


class StatsTests(unittest.TestCase):
    def test_percentage_and_relative_change(self):
        self.assertEqual(S.percentage_point_change(70, 88), -18)
        self.assertAlmostEqual(S.relative_percentage_change(70, 88), -20.45, places=2)

    def test_z_score_and_zero_stdev(self):
        self.assertEqual(S.z_score(10, [5, 5, 5]), 4.5)
        self.assertEqual(S.z_score(5, [5, 5, 5]), 0.0)
        values = [10, 12, 11, 9, 10]
        z = S.z_score(20, values)
        self.assertGreater(z, 2)

    def test_robust_z_and_median_mad(self):
        values = [88, 87, 89, 86, 90, 88, 87, 89]
        rz = S.robust_z_score(69, values)
        self.assertLess(rz, -3)
        self.assertEqual(S.robust_z_score(88, [88, 88, 88]), 0.0)
        self.assertEqual(S.robust_z_score(10, [8, 8, 8]), 4.5)

    def test_anomaly_score_and_severity(self):
        score = S.anomaly_score(pp_change=-18, robust_z=-4, affected_pct=74.5, metric_count=3, confidence=0.8)
        self.assertGreaterEqual(score, 70)
        self.assertLessEqual(score, 100)
        self.assertEqual(S.classify_severity(20), "NORMAL")
        self.assertEqual(S.classify_severity(40), "WATCH")
        self.assertEqual(S.classify_severity(60), "MODERATE")
        self.assertEqual(S.classify_severity(75), "HIGH")
        self.assertEqual(S.classify_severity(90), "CRITICAL")

    def test_affected_percentage_and_safe_math(self):
        self.assertEqual(S.affected_percentage(84, 120), 70.0)
        self.assertEqual(S.affected_percentage(5, 0), 0.0)
        self.assertIsNone(S.safe_div(1, 0))
        self.assertIsNone(S.finite(float("nan")))
        self.assertIsNone(S.finite(float("inf")))
        self.assertEqual(S.relative_percentage_change(0, 0), 0.0)
        self.assertIsNone(S.relative_percentage_change(10, 0))


class EngineTests(unittest.TestCase):
    def test_minimum_cohort_and_empty(self):
        current, weeks = _windows()
        tiny = {
            "students": [{"student_id": 1, "name": "A"}],
            "subjects": [_subject(1, "OS", "IT")],
            "enrollments": _enroll([1], 1),
            "attendance": _sessions([1], 1, current, lambda *_: True) + _sessions([1], 1, weeks[0], lambda *_: True),
            "academic": [],
            "lms": [],
            "institution_name": "X",
        }
        result = engine.analyze(tiny, {"min_cohort_size": 10}, as_of=AS_OF)
        self.assertEqual(result["events"], [])
        self.assertTrue(any(row["reason"] == "insufficient_sample" for row in result["skipped"]))
        empty = engine.analyze({"students": [], "subjects": [], "enrollments": [], "attendance": [], "academic": []}, as_of=AS_OF)
        self.assertEqual(empty["events"], [])
        self.assertTrue(empty["cold_start"])

    def test_high_severity_multi_metric(self):
        result = engine.analyze(high_severity_bundle(), as_of=AS_OF)
        self.assertFalse(result["cold_start"])
        self.assertTrue(result["events"])
        event = max(result["events"], key=lambda row: row["score"])
        self.assertIn(event["severity"], ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(event["score"], 60)
        self.assertIn(event["metric_type"], (engine.METRIC_MULTI, engine.METRIC_ATTENDANCE, engine.METRIC_ASSIGNMENT, engine.METRIC_MARKS))
        self.assertGreaterEqual(event["affected_count"], 70)
        self.assertIn("historical baseline", (event.get("explanation") or "").lower())
        causes = " ".join(item["title"].lower() for item in event.get("possible_causes") or [])
        self.assertNotIn("faculty is responsible", causes)
        self.assertNotIn("caused the problem", causes)
        self.assertTrue(any("course-specific" in item["title"].lower() or "workload" in item["title"].lower() or "scheduling" in item["title"].lower() for item in event.get("possible_causes") or []))

    def test_negative_small_change(self):
        result = engine.analyze(stable_bundle(), as_of=AS_OF)
        self.assertEqual(result["events"], [])

    def test_institution_wide(self):
        result = engine.analyze(institution_wide_bundle(), as_of=AS_OF)
        types = {row["cohort_type"] for row in result["events"]}
        self.assertIn(engine.COHORT_INSTITUTION, types)
        self.assertNotIn(engine.COHORT_COURSE, types)

    def test_course_specific_not_institution(self):
        result = engine.analyze(course_specific_bundle(), as_of=AS_OF)
        self.assertTrue(result["events"])
        types = {row["cohort_type"] for row in result["events"]}
        self.assertIn(engine.COHORT_COURSE, types)
        self.assertNotIn(engine.COHORT_INSTITUTION, types)
        labels = " ".join(row["cohort_label"] for row in result["events"])
        self.assertIn("Operating Systems", labels)
        self.assertNotIn("DBMS", labels)

    def test_data_volume_collapse(self):
        result = engine.analyze(data_failure_bundle(), as_of=AS_OF)
        self.assertTrue(result["events"])
        self.assertTrue(any(row["metric_type"] == engine.METRIC_DATA_QUALITY for row in result["events"]))
        text = " ".join((row.get("explanation") or "") + " ".join(c["title"] for c in row.get("possible_causes") or []) for row in result["events"])
        self.assertNotIn("Students stopped attending", text)
        self.assertTrue("data" in text.lower() or "collection" in text.lower() or any(row.get("collapsed") for row in result["events"]))

    def test_identical_marks_no_crash(self):
        current, weeks = _windows()
        students = list(range(1, 21))
        academic = []
        for window in weeks + [current]:
            academic += _academic(students, 1, window, set(students), 80)
        bundle = {
            "students": [{"student_id": n, "name": f"S{n}"} for n in students],
            "subjects": [_subject(1, "Java", "IT")],
            "enrollments": _enroll(students, 1),
            "attendance": [],
            "academic": academic,
            "lms": [],
        }
        result = engine.analyze(bundle, as_of=AS_OF)
        self.assertEqual(result["events"], [])


class LifecycleTests(unittest.TestCase):
    def test_duplicate_analyze_does_not_clone(self):
        mem = MemoryStore()
        bundle = high_severity_bundle()
        with patch("src.cohort.service.store", mem), patch("src.success.notify.store", mem):
            first = cohort.run_analysis(bundle=bundle, as_of=AS_OF, persist=True, actor="t")
            second = cohort.run_analysis(bundle=bundle, as_of=AS_OF, persist=True, actor="t")
        rows = mem.select("institutional_anomalies")
        self.assertGreaterEqual(len(rows), 1)
        self.assertEqual(len(rows), len({row["identity_key"] for row in rows}))
        self.assertGreaterEqual(second["persist"]["updated"], 1)
        self.assertEqual(first["persist"]["created"], len(rows))

    def test_recovery_resolves(self):
        mem = MemoryStore()
        hot = high_severity_bundle()
        calm = stable_bundle()
        with patch("src.cohort.service.store", mem), patch("src.success.notify.store", mem):
            cohort.run_analysis(bundle=hot, as_of=AS_OF, persist=True, actor="t")
            cohort.save_config({"recovery_periods": 1}, actor="t")
            # Re-run using the same identity population but stable metrics by analyzing calm after rewriting identities
            # Recovery uses open events whose identity is no longer detected.
            cohort.run_analysis(bundle=calm, as_of=AS_OF, persist=True, actor="t")
        open_rows = [row for row in mem.select("institutional_anomalies") if row.get("status") in ("NEW", "INVESTIGATING", "ACKNOWLEDGED")]
        # High-severity OS identity is gone from calm bundle, so it should resolve after 1 recovery period.
        resolved = [row for row in mem.select("institutional_anomalies") if row.get("status") == "RESOLVED"]
        self.assertTrue(resolved or not open_rows or True)
        self.assertTrue(any(row.get("status") == "RESOLVED" for row in mem.select("institutional_anomalies")))


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        self.admin, _ = _bearer("administrator")
        self.student, _ = _bearer("student")
        self.teacher, _ = _bearer("teacher")
        self.counsellor, _ = _bearer("counsellor")
        self.mem = MemoryStore()

    def test_modules_and_student_blocked(self):
        self.assertIn("Institutional Anomalies", _modules("administrator"))
        self.assertIn("Institutional Anomalies", _modules("teacher"))
        self.assertIn("Institutional Anomalies", _modules("counsellor"))
        self.assertNotIn("Institutional Anomalies", _modules("student"))
        denied = self.client.get("/api/institutional-anomalies", headers=self.student)
        self.assertEqual(denied.status_code, 403)

    def test_analyze_list_and_lifecycle(self):
        bundle = high_severity_bundle()
        with patch("src.cohort.service.store", self.mem), patch("src.success.notify.store", self.mem), patch("src.cohort.service.load_classroom_bundle", return_value=bundle):
            analyzed = self.client.post("/api/institutional-anomalies/analyze", headers=self.admin)
            self.assertEqual(analyzed.status_code, 200, analyzed.text)
            listed = self.client.get("/api/institutional-anomalies", headers=self.admin)
            self.assertEqual(listed.status_code, 200)
            rows = listed.json()["anomalies"]
            self.assertTrue(rows)
            anomaly_id = rows[0]["id"]
            one = self.client.get(f"/api/institutional-anomalies/{anomaly_id}", headers=self.admin)
            self.assertEqual(one.status_code, 200)
            self.assertIn("possibleCauses", one.json()["anomaly"])
            ack = self.client.post(f"/api/institutional-anomalies/{anomaly_id}/acknowledge", headers=self.admin)
            self.assertEqual(ack.status_code, 200)
            note = self.client.post(f"/api/institutional-anomalies/{anomaly_id}/notes", headers=self.admin, json={"note": "University event occurred during this period."})
            self.assertEqual(note.status_code, 200)
            counsellor_analyze = self.client.post("/api/institutional-anomalies/analyze", headers=self.counsellor)
            self.assertEqual(counsellor_analyze.status_code, 403)
            counsellor_view = self.client.get("/api/institutional-anomalies", headers=self.counsellor)
            self.assertEqual(counsellor_view.status_code, 200)


if __name__ == "__main__":
    unittest.main()
