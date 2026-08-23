"""Institutional dropout root-cause: statistics, engine, privacy, API."""

from __future__ import annotations

import math
import unittest
from datetime import datetime
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import _modules, router
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.dropout import engine
from src.dropout import service as dropout
from src.dropout import stats as S


AS_OF = datetime(2026, 6, 1, 12, 0, 0)
BEFORE = "2026-01-15T10:00:00+00:00"
AFTER = "2026-07-15T10:00:00+00:00"
OUTCOME_AT = "2026-06-01T12:00:00+00:00"


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


def _students(n):
    return [{"student_id": sid, "name": f"S{sid}"} for sid in range(1, n + 1)]


def _sessions(student_ids, subject_id, present_fn, count=3, stamp=BEFORE):
    logs = []
    for index in range(count):
        for sid in student_ids:
            logs.append({
                "student_id": sid,
                "subject_id": subject_id,
                "timestamp": stamp,
                "is_present": bool(present_fn(sid, index)),
            })
    return logs


def _outcomes(ids, status="DROPPED_OUT", period="2026"):
    return [{
        "student_id": sid,
        "status": status,
        "period": period,
        "recorded_at": OUTCOME_AT,
    } for sid in ids]


def _academic(student_ids, subject_id, score, semester, stamp=BEFORE):
    return [{
        "student_id": sid,
        "subject_id": subject_id,
        "semester": semester,
        "score": score,
        "max_score": 100,
        "recorded_at": stamp,
    } for sid in student_ids]


def attendance_bundle():
    students = list(range(1, 1001))
    low = set(range(1, 201))
    dropouts = list(range(1, 61)) + list(range(201, 261))
    return {
        "students": _students(1000),
        "subjects": [{"subject_id": 1, "name": "DSA", "subject_code": "DSA", "section": "IT", "teacher_id": 1}],
        "enrollments": [{"student_id": sid, "subject_id": 1} for sid in students],
        "attendance": _sessions(students, 1, lambda sid, index: (sid not in low) or index == 0),
        "academic": [],
        "lms": [],
        "outcomes": _outcomes(dropouts),
        "institution_name": "CLASSORA Demo University",
    }


def repeated_failure_bundle():
    failed = list(range(1, 151))
    others = list(range(151, 1001))
    dropouts = list(range(1, 61)) + list(range(151, 211))
    academic = []
    academic += _academic(failed, 1, 20, "4")
    academic += _academic(failed, 1, 18, "4", stamp="2026-02-01T10:00:00+00:00")
    academic += _academic(others, 1, 80, "4")
    return {
        "students": _students(1000),
        "subjects": [{"subject_id": 1, "name": "DBMS", "subject_code": "DBMS", "section": "IT", "teacher_id": 1}],
        "enrollments": [{"student_id": sid, "subject_id": 1} for sid in range(1, 1001)],
        "attendance": [],
        "academic": academic,
        "lms": [],
        "outcomes": _outcomes(dropouts),
        "institution_name": "CLASSORA Demo University",
    }


def first_year_bundle():
    first = list(range(1, 501))
    later = list(range(501, 1001))
    dropouts = list(range(1, 91)) + list(range(501, 531))
    academic = _academic(first, 1, 75, "1") + _academic(later, 1, 75, "5")
    return {
        "students": _students(1000),
        "subjects": [{"subject_id": 1, "name": "Java", "subject_code": "JAVA", "section": "CSE", "teacher_id": 1}],
        "enrollments": [{"student_id": sid, "subject_id": 1} for sid in range(1, 1001)],
        "attendance": [],
        "academic": academic,
        "lms": [],
        "outcomes": _outcomes(dropouts),
        "institution_name": "CLASSORA Demo University",
    }


def course_bundle():
    os_students = list(range(1, 201))
    other = list(range(201, 1001))
    dropouts = list(range(1, 41)) + list(range(201, 281))
    return {
        "students": _students(1000),
        "subjects": [
            {"subject_id": 1, "name": "Operating Systems", "subject_code": "OS", "section": "IT", "teacher_id": 1},
            {"subject_id": 2, "name": "DBMS", "subject_code": "DBMS", "section": "CSE", "teacher_id": 2},
        ],
        "enrollments": (
            [{"student_id": sid, "subject_id": 1} for sid in os_students]
            + [{"student_id": sid, "subject_id": 2} for sid in other]
        ),
        "attendance": [],
        "academic": _academic(os_students, 1, 70, "4") + _academic(other, 2, 70, "4"),
        "lms": [],
        "outcomes": _outcomes(dropouts),
        "institution_name": "CLASSORA Demo University",
    }


def uniform_bundle():
    dropouts = list(range(1, 21))
    students = list(range(1, 101))
    return {
        "students": _students(100),
        "subjects": [{"subject_id": 1, "name": "COA", "subject_code": "COA", "section": "ECE", "teacher_id": 1}],
        "enrollments": [{"student_id": sid, "subject_id": 1} for sid in students],
        "attendance": _sessions(students, 1, lambda sid, index: True),
        "academic": _academic(students, 1, 80, "3"),
        "lms": [],
        "outcomes": _outcomes(dropouts),
        "institution_name": "CLASSORA Demo University",
    }


def leakage_bundle():
    return {
        "students": _students(20),
        "subjects": [{"subject_id": 1, "name": "DSA", "subject_code": "DSA", "section": "IT", "teacher_id": 1}],
        "enrollments": [{"student_id": sid, "subject_id": 1} for sid in range(1, 21)],
        "attendance": (
            _sessions(range(1, 21), 1, lambda sid, index: True, stamp=BEFORE)
            + _sessions([1], 1, lambda sid, index: False, count=8, stamp=AFTER)
        ),
        "academic": _academic(range(1, 21), 1, 80, "4") + [{
            "student_id": 1,
            "subject_id": 1,
            "semester": "4",
            "score": 10,
            "max_score": 100,
            "recorded_at": AFTER,
        }],
        "lms": [],
        "outcomes": _outcomes(list(range(1, 13))),
        "institution_name": "CLASSORA Demo University",
    }


class StatsTests(unittest.TestCase):
    def test_attendance_formulas(self):
        self.assertEqual(S.dropout_rate(60, 200), 30.0)
        self.assertEqual(S.dropout_rate(60, 800), 7.5)
        self.assertEqual(S.dropout_rate(120, 1000), 12.0)
        self.assertEqual(S.relative_risk(30.0, 7.5), 4.0)
        self.assertEqual(S.risk_difference(30.0, 7.5), 22.5)

    def test_no_nan_or_inf(self):
        self.assertIsNone(S.dropout_rate(1, 0))
        self.assertIsNone(S.relative_risk(10, 0))
        self.assertIsNone(S.relative_risk(None, 5))
        values = [
            S.dropout_rate(0, 0),
            S.odds_ratio(0, 0, 0, 0),
            S.chi_square_2x2(0, 0, 0, 0)[0],
            S.fisher_exact_2x2(0, 0, 0, 0),
        ]
        for value in values:
            if value is not None:
                self.assertFalse(math.isnan(value) or math.isinf(value))

    def test_confidence_and_sample_guard(self):
        self.assertEqual(S.confidence_label(exposed_n=3, comparison_n=80, p_value=0.01, min_n=10), "INSUFFICIENT_DATA")
        self.assertEqual(S.classify_factor(relative_risk=4, risk_diff=22, trend="STABLE", confidence="HIGH"), "SIGNIFICANT")
        self.assertEqual(S.classify_trend([18, 21, 32]), "EMERGING")


class EngineTests(unittest.TestCase):
    def test_attendance_scenario(self):
        result = engine.analyze(attendance_bundle())
        self.assertFalse(result["insufficient"])
        factor = next(f for f in result["factors"] if f["factorId"] == "LOW_ATTENDANCE")
        self.assertEqual(factor["dropoutRate"], 30.0)
        self.assertEqual(factor["comparisonRate"], 7.5)
        self.assertEqual(factor["baselineDropoutRate"], 12.0)
        self.assertEqual(factor["relativeRisk"], 4.0)
        self.assertEqual(factor["riskDifference"], 22.5)
        self.assertIn("association", factor["evidence"].lower())
        self.assertNotIn("caused these students", factor["evidence"].lower())

    def test_repeated_failure_scenario(self):
        result = engine.analyze(repeated_failure_bundle())
        factor = next(f for f in result["factors"] if f["factorId"] == "REPEATED_FAILURE")
        self.assertAlmostEqual(factor["dropoutRate"], 40.0, places=1)
        self.assertAlmostEqual(factor["comparisonRate"], 7.06, places=1)
        self.assertGreaterEqual(factor["relativeRisk"], 5)

    def test_first_year_scenario(self):
        result = engine.analyze(first_year_bundle())
        factor = next(f for f in result["factors"] if f["factorId"] == "FIRST_YEAR")
        self.assertEqual(factor["dropoutRate"], 18.0)
        self.assertEqual(factor["comparisonRate"], 6.0)
        self.assertEqual(result["firstYearShare"], 75.0)

    def test_course_concentration_without_blame(self):
        result = engine.analyze(course_bundle())
        course = next(f for f in result["factors"] if str(f.get("factorId")).startswith("COURSE_"))
        self.assertEqual(course["dropoutRate"], 20.0)
        self.assertEqual(course["comparisonRate"], 10.0)
        text = " ".join(f.get("evidence") or "" for f in result["factors"])
        self.assertIn("associated with this course", text.lower())
        self.assertNotIn("operating systems caused", text.lower())
        self.assertIn("not a finding that the course or faculty caused dropout", text.lower())

    def test_financial_not_invented(self):
        result = engine.analyze(attendance_bundle())
        self.assertFalse(result["unavailable"]["FINANCIAL"]["available"])
        self.assertEqual(result["unavailable"]["FINANCIAL"]["status"], "NOT_AVAILABLE")
        self.assertTrue(any(f["factorId"] == "LOW_ATTENDANCE" for f in result["factors"]))
        self.assertFalse(any("FINANCIAL" in str(f.get("factorId")) for f in result["factors"]))

    def test_no_dominant_factor(self):
        result = engine.analyze(uniform_bundle())
        self.assertTrue(result["noDominantFactor"])
        self.assertIn("No dominant dropout-associated factor", result["emptyMessage"])

    def test_insufficient_two_dropouts(self):
        bundle = attendance_bundle()
        bundle["outcomes"] = _outcomes([1, 2])
        result = engine.analyze(bundle)
        self.assertTrue(result["insufficient"])
        self.assertEqual(result["factors"], [])
        self.assertIn("Insufficient historical dropout data", result["reason"])

    def test_zero_students_and_zero_dropouts(self):
        empty = engine.analyze({"students": [], "subjects": [], "enrollments": [], "attendance": [], "academic": [], "lms": [], "outcomes": []})
        self.assertTrue(empty["insufficient"])
        none = engine.analyze({**attendance_bundle(), "outcomes": []})
        self.assertTrue(none["insufficient"])
        self.assertEqual(none["overview"]["dropouts"], 0)

    def test_all_dropped_no_crash(self):
        bundle = uniform_bundle()
        bundle["outcomes"] = _outcomes(list(range(1, 101)))
        result = engine.analyze(bundle)
        self.assertEqual(result["overview"]["dropoutRate"], 100.0)
        self._assert_finite(result)

    def _assert_finite(self, value):
        if isinstance(value, dict):
            for item in value.values():
                self._assert_finite(item)
            return
        if isinstance(value, list):
            for item in value:
                self._assert_finite(item)
            return
        if isinstance(value, float):
            self.assertFalse(math.isnan(value) or math.isinf(value), value)

    def test_small_group_suppressed(self):
        bundle = uniform_bundle()
        bundle["subjects"].append({"subject_id": 9, "name": "Tiny", "subject_code": "T", "section": "ZZ", "teacher_id": 9})
        bundle["enrollments"] += [{"student_id": sid, "subject_id": 9} for sid in range(1, 4)]
        result = engine.analyze(bundle)
        tiny = next(row for row in result["slices"]["sections"] if row["id"] == "ZZ")
        self.assertTrue(tiny["suppressed"])
        self.assertIn("suppressed", tiny["label"].lower())

    def test_missing_attendance_not_low_attendance(self):
        result = engine.analyze(first_year_bundle())
        self.assertEqual(result["unavailable"]["LOW_ATTENDANCE"]["status"], "NOT_AVAILABLE")
        self.assertIn("Attendance data unavailable", result["unavailable"]["LOW_ATTENDANCE"]["reason"])

    def test_no_future_leakage(self):
        profiles, _subjects = engine.build_profiles(leakage_bundle(), engine.normalize_config())
        student = next(p for p in profiles if p["student_id"] == 1)
        self.assertEqual(student["attendance"], 100.0)
        self.assertFalse(student["failed"])
        self.assertGreater(student["avg_marks"], 40)


class PersistenceTests(unittest.TestCase):
    def test_analyze_is_idempotent(self):
        mem = MemoryStore()
        bundle = attendance_bundle()
        with patch("src.dropout.service.store", mem), patch("src.success.notify.store", mem):
            first = dropout.run_analysis(bundle=bundle, persist=True, actor="t")
            second = dropout.run_analysis(bundle=bundle, persist=True, actor="t")
        rows = mem.select("institutional_dropout_analyses")
        self.assertEqual(len(rows), 1)
        self.assertEqual(first["persist"]["analysisId"], second["persist"]["analysisId"])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = _client()
        self.admin, _ = _bearer("administrator")
        self.student, _ = _bearer("student")
        self.teacher, _ = _bearer("teacher")
        self.counsellor, _ = _bearer("counsellor")
        self.faculty, _ = _bearer("faculty")
        self.mem = MemoryStore()

    def test_modules_and_rbac(self):
        self.assertIn("Dropout Root Causes", _modules("administrator"))
        self.assertIn("Dropout Root Causes", _modules("teacher"))
        self.assertNotIn("Dropout Root Causes", _modules("counsellor"))
        self.assertNotIn("Dropout Root Causes", _modules("student"))
        self.assertNotIn("Dropout Root Causes", _modules("faculty"))
        self.assertEqual(self.client.get("/api/institutional-dropout/overview", headers=self.student).status_code, 403)
        self.assertEqual(self.client.get("/api/institutional-dropout/overview", headers=self.counsellor).status_code, 403)
        self.assertEqual(self.client.get("/api/institutional-dropout/overview", headers=self.faculty).status_code, 403)

    def test_admin_analyze_and_read(self):
        bundle = attendance_bundle()
        with patch("src.dropout.service.store", self.mem), patch("src.success.notify.store", self.mem), patch("src.dropout.service.load_bundle", return_value=bundle):
            analyzed = self.client.post("/api/institutional-dropout/analyze", headers=self.admin)
            self.assertEqual(analyzed.status_code, 200, analyzed.text)
            overview = self.client.get("/api/institutional-dropout/overview", headers=self.admin)
            self.assertEqual(overview.status_code, 200)
            self.assertFalse(overview.json()["insufficient"])
            factors = self.client.get("/api/institutional-dropout/factors", headers=self.admin)
            self.assertEqual(factors.status_code, 200)
            self.assertTrue(any(row["factorId"] == "LOW_ATTENDANCE" for row in factors.json()["factors"]))
            one = self.client.get("/api/institutional-dropout/factors/LOW_ATTENDANCE", headers=self.admin)
            self.assertEqual(one.status_code, 200)
            self.assertIn("association", one.json()["factor"]["evidence"].lower())
            departments = self.client.get("/api/institutional-dropout/departments", headers=self.admin)
            self.assertTrue(departments.json()["unavailable"])
            self.assertEqual(departments.json()["dimension"], "section")
            counsellor = self.client.post("/api/institutional-dropout/analyze", headers=self.counsellor)
            self.assertEqual(counsellor.status_code, 403)


if __name__ == "__main__":
    unittest.main()
