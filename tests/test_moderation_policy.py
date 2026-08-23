"""Authorization and privacy rules for the complaint / ban system."""

import unittest

from src.moderation import policy as P
from src.moderation.service import (
    admin_decide,
    admin_open,
    create_complaint,
    public_complaint_id,
    request_information,
    review_appeal,
)


class FacultyCannotExecuteTests(unittest.TestCase):
    def test_faculty_may_create_but_not_ban(self):
        self.assertTrue(P.can_create_complaint("faculty"))
        self.assertTrue(P.can_create_complaint("mentor"))
        self.assertTrue(P.can_create_complaint("teacher"))
        self.assertFalse(P.can_execute_moderation("faculty"))
        self.assertFalse(P.can_execute_moderation("mentor"))
        self.assertFalse(P.can_execute_moderation("teacher"))
        self.assertFalse(P.can_execute_moderation("counsellor"))
        self.assertFalse(P.can_review_complaints("faculty"))
        self.assertTrue(P.can_execute_moderation("administrator"))
        self.assertTrue(P.can_review_complaints("administrator"))

    def test_request_ban_is_not_execute_ban(self):
        self.assertIn("student_id_ban", P.REQUESTED_ACTIONS.values())
        self.assertIn("ban", P.EXECUTE_ACTIONS)
        self.assertNotEqual("student_id_ban", "ban")
        err = P.faculty_cannot_execute("ban", "faculty")
        self.assertIsNotNone(err)
        self.assertIn("administrator", err.lower())
        self.assertIsNone(P.faculty_cannot_execute("ban", "administrator"))

    def test_service_rejects_faculty_ban(self):
        ok, msg = admin_decide(
            complaint_id="00000000-0000-0000-0000-000000000000",
            admin_staff_id=1,
            admin_role="faculty",
            action="ban",
            reason="should not work",
            confirm_ban=True,
        )
        self.assertIsNone(ok)
        self.assertIn("administrator", msg.lower())

    def test_service_rejects_faculty_investigation(self):
        dossier, msg = admin_open("x", 1, "faculty")
        self.assertIsNone(dossier)
        self.assertIn("administrator", msg.lower())

    def test_service_rejects_faculty_info_request(self):
        ok, msg = request_information("x", 1, "faculty", "need more")
        self.assertIsNone(ok)

    def test_service_rejects_faculty_appeal_review(self):
        ok, msg = review_appeal(
            appeal_id=1, admin_staff_id=1, admin_role="mentor",
            decision="accept", admin_note="nope",
        )
        self.assertIsNone(ok)


class AnonymousIdentityTests(unittest.TestCase):
    def test_faculty_payload_strips_identity(self):
        leaked = P.strip_faculty_payload({
            "complaintCode": "CMP-ABC123",
            "student_id": 99,
            "name": "Secret Student",
            "email": "s@campus.edu",
            "phone": "999",
            "adminNotes": "confidential",
            "status": "Submitted",
        })
        self.assertEqual(leaked["complaintCode"], "CMP-ABC123")
        self.assertNotIn("student_id", leaked)
        self.assertNotIn("name", leaked)
        self.assertNotIn("email", leaked)
        self.assertNotIn("phone", leaked)
        self.assertNotIn("adminNotes", leaked)

    def test_faculty_status_hides_admin_outcomes(self):
        self.assertEqual(P.faculty_status_label("SUBMITTED"), "Submitted")
        self.assertEqual(P.faculty_status_label("UNDER_REVIEW"), "Under Review")
        self.assertEqual(P.faculty_status_label("INFO_REQUIRED"), "Additional Information Required")
        self.assertEqual(P.faculty_status_label("DISMISSED"), "Dismissed")
        self.assertEqual(P.faculty_status_label("WARNING_ISSUED"), "Action Taken")
        self.assertEqual(P.faculty_status_label("BANNED"), "Action Taken")
        self.assertEqual(P.faculty_status_label("RESTRICTED"), "Action Taken")


class BanLoginTests(unittest.TestCase):
    def test_banned_cannot_login_restricted_can(self):
        self.assertFalse(P.login_allowed_for("BANNED"))
        self.assertFalse(P.login_allowed_for("SUSPENDED"))
        self.assertTrue(P.login_allowed_for("RESTRICTED"))
        self.assertTrue(P.login_allowed_for("ACTIVE"))
        self.assertFalse(P.can_participate("RESTRICTED"))
        self.assertFalse(P.can_participate("BANNED"))
        self.assertTrue(P.can_appeal("BANNED"))
        self.assertFalse(P.can_appeal("ACTIVE"))

    def test_ban_requires_confirmation_flag(self):
        ok, msg = admin_decide(
            complaint_id="00000000-0000-0000-0000-000000000000",
            admin_staff_id=1,
            admin_role="administrator",
            action="ban",
            reason="confirmed policy reason",
            confirm_ban=False,
        )
        self.assertIsNone(ok)
        self.assertIn("Confirmation", msg)


class EvidenceAndComplaintCreateTests(unittest.TestCase):
    def test_evidence_type_and_size(self):
        self.assertIsNone(P.validate_evidence("note.txt", "text/plain", 100))
        self.assertIsNotNone(P.validate_evidence("note.exe", "application/octet-stream", 100))
        self.assertIsNotNone(P.validate_evidence("big.pdf", "application/pdf", P.MAX_EVIDENCE_BYTES + 1))

    def test_unauthorized_cannot_create(self):
        payload, err = create_complaint(
            reporter_role="student",
            reporter_staff_id=1,
            student_reference="STU-AAAA1111",
            category=P.CATEGORIES[0],
            severity="high",
            description="This is a long enough description of misconduct.",
            requested_action="student_id_ban",
        )
        self.assertIsNone(payload)
        self.assertIn("faculty", err.lower())

    def test_student_cannot_request_ban_as_execute(self):
        self.assertFalse(P.can_execute_moderation("student"))
        self.assertFalse(P.can_create_complaint("student"))
        self.assertFalse(P.can_create_complaint("administrator"))

    def test_public_complaint_id_is_stable_code(self):
        self.assertEqual(public_complaint_id({
            "complaint_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "complaint_code": "CMP-AB12CD34",
        }), "CMP-AB12CD34")
        derived = public_complaint_id({"complaint_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"})
        self.assertTrue(derived.startswith("CMP-"))
        self.assertEqual(derived, public_complaint_id({"complaint_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}))


if __name__ == "__main__":
    unittest.main()
