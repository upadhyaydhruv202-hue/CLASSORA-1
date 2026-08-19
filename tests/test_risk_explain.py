"""Explainable risk, recovery counterfactuals, trajectory, and twin payloads."""

import unittest

from src.mentorship.service import IDENTITY_KEYS, faculty_view, strip_identity
from src.moderation.policy import can_execute_moderation, strip_faculty_payload
from src.success.demo_data import demo_students
from src.success.intelligence import profile_map
from src.success.risk_model import (
    academic_features,
    attendance_features,
    engagement_features,
    explain_drivers,
    narrative_why,
    project_trajectory,
    recovery_scenarios,
    score_student,
    simulate_changes,
    temporal_features,
)
from src.success.twin import build_twin


def _demo_profiles():
    data = demo_students("multiple")
    data["demo"] = True
    return profile_map(data)


class ExplainableAiTests(unittest.TestCase):
    def test_drivers_are_exact_additives_and_sum_to_100(self):
        att = {"rate": 50, "consecutive_absences": 4, "sudden_decline": 25, "chronic": True, "marked": 12, "present": 6, "absent": 6}
        aca = academic_features([{"score": 30, "max_score": 100, "backlog": True}])
        eng = {"count": 1, "inactive_days": 20, "trend": "low"}
        pred = score_student(att, aca, eng)
        self.assertTrue(pred["drivers"])
        total = round(sum(d["percent"] for d in pred["drivers"]), 0)
        self.assertTrue(90 <= total <= 110)
        self.assertTrue(any(d["name"] == "Attendance Decline" and d["percent"] > 0 for d in pred["drivers"]))
        self.assertIn("exact additives", narrative_why(att, aca, eng, pred)["method"].lower())

    def test_method_does_not_claim_shap(self):
        att = attendance_features([])
        pred = score_student(att, academic_features([]), engagement_features([]))
        text = narrative_why(att, academic_features([]), engagement_features([]), pred)["method"]
        self.assertIn("SHAP/LIME are not applied", text)
        self.assertIn("exact additives", narrative_why(att, academic_features([]), engagement_features([]), pred)["method"])

    def test_student_narrative_has_no_other_student(self):
        att = {"rate": 60, "consecutive_absences": 0, "sudden_decline": 18, "chronic": False, "marked": 12, "present": 7, "absent": 5}
        pred = score_student(att, academic_features([]), engagement_features([]))
        narr = narrative_why(att, academic_features([]), engagement_features([]), pred, role="student")
        blob = " ".join(narr["why"] + narr["recommended"]).lower()
        self.assertNotIn("faculty name", blob)
        self.assertNotIn("ban", blob)


class RecoveryAiTests(unittest.TestCase):
    def test_attendance_improvement_lowers_score(self):
        att = {"rate": 62, "consecutive_absences": 3, "sudden_decline": 20, "chronic": False, "marked": 12, "present": 7, "absent": 5}
        aca = academic_features([{"score": 58, "max_score": 100}])
        eng = {"count": 1, "inactive_days": 2, "trend": "ok"}
        current = score_student(att, aca, eng)
        better = simulate_changes(att, aca, eng, {"attendance_delta": 13}, current=current)
        self.assertEqual(better["label"], "SIMULATED / ESTIMATED")
        self.assertLess(better["estimated_score"], current["score"])

    def test_mentorship_is_associated_support_not_magic(self):
        att = {"rate": 62, "consecutive_absences": 0, "sudden_decline": 0, "chronic": False, "marked": 12, "present": 7, "absent": 5}
        aca = academic_features([])
        eng = engagement_features([])
        off = score_student(att, aca, eng, support={"mentorship_active": False})
        on = score_student(att, aca, eng, support={"mentorship_active": True})
        self.assertLess(on["score"], off["score"])
        self.assertAlmostEqual(off["score"] - on["score"], 8, delta=0.2)

    def test_recovery_pack_is_labeled_simulated(self):
        att = {"rate": 62, "consecutive_absences": 3, "sudden_decline": 22, "chronic": False, "marked": 12, "present": 7, "absent": 5}
        pack = recovery_scenarios(att, academic_features([{"score": 50, "max_score": 100}]), engagement_features([]))
        self.assertEqual(pack["label"], "SIMULATED / ESTIMATED")
        self.assertTrue(pack["scenarios"])
        self.assertIsNotNone(pack["minimum_practical"])


class TrajectoryTests(unittest.TestCase):
    def test_insufficient_history_is_not_fabricated(self):
        att = {"rate": 70, "consecutive_absences": 0, "sudden_decline": None, "chronic": False, "marked": 3, "present": 2, "absent": 1}
        traj = project_trajectory(att, academic_features([]), engagement_features([]))
        self.assertTrue(traj["insufficient_history"])
        self.assertEqual(traj["label"], "INSUFFICIENT HISTORY")
        self.assertEqual(len(traj["points"]), 1)

    def test_with_decline_has_7_30_60(self):
        att = {"rate": 64, "consecutive_absences": 2, "sudden_decline": 18, "chronic": False, "marked": 12, "present": 8, "absent": 4}
        traj = project_trajectory(att, academic_features([]), engagement_features([]))
        self.assertFalse(traj["insufficient_history"])
        days = [p["days"] for p in traj["points"]]
        self.assertEqual(days, [0, 7, 30, 60])
        self.assertIn("SIMULATED", traj["label"])

    def test_temporal_distinguishes_deterioration(self):
        low = temporal_features({"rate": 55, "sudden_decline": 4})
        rapid = temporal_features({"rate": 55, "sudden_decline": 20})
        self.assertEqual(low["pattern"], "currently_low")
        self.assertEqual(rapid["pattern"], "rapidly_deteriorating")


class TwinAndPrivacyTests(unittest.TestCase):
    def test_demo_profiles_score_without_writing(self):
        rows = _demo_profiles()
        self.assertTrue(rows)
        priya = next(p for p in rows if p["student_id"] == -105)
        self.assertIn(priya["prediction"]["category"], ("Watch", "High", "Critical", "Stable"))
        self.assertTrue(priya["prediction"].get("drivers"))

    def test_student_twin_omits_faculty_identity(self):
        rows = _demo_profiles()
        p = rows[0]
        twin = build_twin(p, role="student")
        blob = str(twin)
        self.assertNotIn("password", blob)
        self.assertNotIn("email", blob.lower() if "email" in blob.lower() else blob)
        self.assertIn("anonymousMentorId", twin["mentorship"])
        self.assertNotIn("mentorName", twin.get("mentorship", {}))
        self.assertNotIn("scenarios", twin)

    def test_faculty_payload_cannot_carry_hidden_identity(self):
        leaked = strip_faculty_payload({"complaintCode": "CMP-1", "name": "Rahul", "student_id": 9})
        self.assertNotIn("name", leaked)
        self.assertNotIn("student_id", leaked)

    def test_mentorship_strip_identity_keys(self):
        payload = strip_identity({"anonymousStudentId": "STU-1", "name": "Secret", "student_id": 3, "email": "x"})
        self.assertEqual(payload["anonymousStudentId"], "STU-1")
        for key in ("name", "student_id", "email"):
            self.assertNotIn(key, payload)
        self.assertTrue(IDENTITY_KEYS)

    def test_faculty_view_denies_wrong_staff_without_leaking(self):
        view = faculty_view("00000000-0000-0000-0000-000000000000", 999999)
        self.assertIsNone(view)

    def test_faculty_still_cannot_ban(self):
        self.assertFalse(can_execute_moderation("faculty"))
        self.assertFalse(can_execute_moderation("student"))


class ExplainDriversUnit(unittest.TestCase):
    def test_empty_contributors(self):
        drivers = explain_drivers({"contributors": []})
        self.assertIsInstance(drivers, list)


if __name__ == "__main__":
    unittest.main()
