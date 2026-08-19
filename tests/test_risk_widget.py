"""Live risk widget: real scorer, cached fingerprints, RBAC, threshold mapping."""

import unittest

from src.success.risk_model import score_student, widget_level, widget_level_label
from src.success.risk_service import _can_read, fingerprint, get_current_risk


class WidgetThresholdTests(unittest.TestCase):
    def test_uses_production_critical_and_watch_cutovers(self):
        self.assertEqual(widget_level(0, "Stable"), "LOW")
        self.assertEqual(widget_level(29, "Stable"), "LOW")
        self.assertEqual(widget_level(30, "Watch"), "MODERATE")
        self.assertEqual(widget_level(39, "Watch"), "MODERATE")
        self.assertEqual(widget_level(40, "Watch"), "MODERATE")
        self.assertEqual(widget_level(50, "High"), "MODERATE")
        self.assertEqual(widget_level(69, "High"), "MODERATE")
        self.assertEqual(widget_level(70, "Critical"), "HIGH")
        self.assertEqual(widget_level(100, "Critical"), "HIGH")
        self.assertEqual(widget_level_label("HIGH"), "HIGH RISK")

    def test_score_student_attaches_widget_level(self):
        att = {"rate": 40, "consecutive_absences": 5, "sudden_decline": 25, "chronic": True, "marked": 12, "present": 5, "absent": 7}
        pred = score_student(att, {"gpa": None, "failed": 2, "backlogs": 1, "avg_score": 32, "count": 2, "completion": 50}, {"count": 1, "inactive_days": 20, "trend": "low"})
        self.assertIn(pred["widgetLevel"], ("LOW", "MODERATE", "HIGH"))
        self.assertEqual(pred["widgetLevel"], widget_level(pred["score"], pred["category"]))


class RiskServiceAuthTests(unittest.TestCase):
    def test_student_cannot_read_another_student(self):
        self.assertFalse(_can_read(actor_role="student", actor_student_id=1, actor_teacher_id=None, student_id=2))
        self.assertTrue(_can_read(actor_role="student", actor_student_id=7, actor_teacher_id=None, student_id=7))

    def test_get_current_risk_rejects_cross_student(self):
        payload = get_current_risk(
            99,
            session_state={},
            actor_role="student",
            actor_student_id=1,
        )
        self.assertTrue(payload.get("unauthorized"))
        self.assertIsNone(payload.get("riskScore"))

    def test_fingerprint_changes_when_attendance_changes(self):
        base = {
            "student_id": 1,
            "attendance": {"marked": 10, "present": 6, "rate": 60, "sudden_decline": 0, "consecutive_absences": 0},
            "academic": {"count": 0, "avg_score": None, "failed": 0, "completion": None},
            "engagement": {"count": 0, "inactive_days": None},
            "mentorship_active": False,
            "prediction": {"model_version": "success-risk-v1.1"},
        }
        a = fingerprint(base)
        b = dict(base)
        b["attendance"] = {**base["attendance"], "rate": 68, "present": 7}
        self.assertNotEqual(a, fingerprint(b))


class CacheSkipRescoreTests(unittest.TestCase):
    def test_missing_student_does_not_invent_a_score(self):
        payload = get_current_risk(
            9_999_999,
            session_state={},
            actor_role="student",
            actor_student_id=9_999_999,
        )
        if payload.get("available"):
            self.fail("Should not mark a nonexistent student as an available live score")
        self.assertIsNone(payload.get("riskScore"))


if __name__ == "__main__":
    unittest.main()
