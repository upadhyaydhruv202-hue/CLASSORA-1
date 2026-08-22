"""Authorization, expiry, isolation, and workflow checks for existing Success Hub APIs."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from src.api.app import success_hub, success_student
from src.api.features import (
    _alerts,
    _duplicate_import_row,
    router,
    success_alert_resolve,
    success_search,
    success_settings_get,
    success_task_done,
)
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.database.db import hash_pass
from src.success.intelligence import _owned
from src.success.ops import parse_import_csv
from src.success.staff_auth import activate_staff, invite_staff


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


class InviteLifecycleTests(unittest.TestCase):
    def test_empty_invite_rejected(self):
        token, msg = invite_staff(" ", "user", "counsellor", 1)
        self.assertIsNone(token)
        self.assertIn("required", msg.lower())

    def test_expired_invite_rejected(self):
        token = "old-code"
        invite = {
            "invite_id": 2,
            "invited_username": "alex",
            "token_hash": hash_pass(token),
            "used_at": None,
            "expires_at": (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(),
            "assigned_role": "counsellor",
            "invited_name": "Alex",
        }
        with patch("src.success.staff_auth.store.select", return_value=[invite]):
            staff, msg = activate_staff("alex", token, "Password1!", "Password1!")
        self.assertIsNone(staff)
        self.assertIn("expired", msg.lower())

    def test_used_invite_rejected(self):
        token = "used-code"
        invite = {
            "invite_id": 3,
            "invited_username": "alex",
            "token_hash": hash_pass(token),
            "used_at": datetime.now(timezone.utc).isoformat(),
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
            "assigned_role": "counsellor",
            "invited_name": "Alex",
        }
        with patch("src.success.staff_auth.store.select", return_value=[invite]):
            staff, msg = activate_staff("alex", token, "Password1!", "Password1!")
        self.assertIsNone(staff)
        self.assertIn("already been used", msg.lower())

    def test_empty_code_rejected(self):
        staff, msg = activate_staff("alex", "  ", "Password1!", "Password1!")
        self.assertIsNone(staff)
        self.assertIn("required", msg.lower())


class AlertAndImportTests(unittest.TestCase):
    def test_resolved_alerts_do_not_reappear(self):
        profiles = [{
            "name": "Ada",
            "student_id": 1,
            "prediction": {"category": "High"},
            "attendance": {"consecutive_absences": 0},
        }]
        with patch("src.api.features.store.select", return_value=[{
            "student_id": 1,
            "title": "Predicted High risk",
            "status": "resolved",
        }]):
            self.assertEqual(_alerts(profiles), [])

    def test_unresolved_high_risk_still_alerts(self):
        profiles = [{
            "name": "Ada",
            "student_id": 1,
            "prediction": {"category": "High"},
            "attendance": {"consecutive_absences": 0},
        }]
        with patch("src.api.features.store.select", return_value=[]):
            rows = _alerts(profiles)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Predicted High risk")

    def test_duplicate_academic_row_detected(self):
        row = {"student_id": 7, "assessment": "Midterm", "score": 18.0}
        existing = [{"student_id": 7, "assessment": "Midterm", "score": 18.0}]
        self.assertTrue(_duplicate_import_row("academic_records", row, existing))
        self.assertFalse(_duplicate_import_row("academic_records", {**row, "score": 19.0}, existing))

    def test_csv_missing_student_id(self):
        rows, err = parse_import_csv("assessment,score\nMidterm,10\n", "academic")
        self.assertEqual(rows, [])
        self.assertIn("student_id", err)

    def test_teacher_rows_are_roster_scoped(self):
        rows = _owned(
            [{"student_id": 1, "assessment": "A"}, {"student_id": 99, "assessment": "B"}],
            {1},
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["student_id"], 1)


class AuthorizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app = FastAPI()
        app.include_router(router)
        cls.client = TestClient(app)

    def test_search_requires_auth(self):
        res = self.client.get("/api/success/search?q=ada")
        self.assertEqual(res.status_code, 401)

    def test_report_requires_auth(self):
        res = self.client.get("/api/success/report")
        self.assertEqual(res.status_code, 401)

    def test_settings_requires_auth(self):
        res = self.client.get("/api/success/settings")
        self.assertEqual(res.status_code, 401)

    def test_student_cannot_search(self):
        headers, session = _bearer("student", student_id=1)
        res = self.client.get("/api/success/search?q=ada", headers=headers)
        self.assertEqual(res.status_code, 403)
        with self.assertRaises(HTTPException) as ctx:
            success_search(q="ada", session=session)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_student_cannot_open_settings_or_hub(self):
        _, session = _bearer("student", student_id=1)
        with self.assertRaises(HTTPException) as ctx:
            success_settings_get(session=session)
        self.assertEqual(ctx.exception.status_code, 403)
        with self.assertRaises(HTTPException) as ctx:
            success_hub(session=session)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_student_cannot_read_another_student(self):
        _, session = _bearer("student", student_id=1)
        with self.assertRaises(HTTPException) as ctx:
            success_student(2, session=session)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_student_cannot_resolve_alerts(self):
        _, session = _bearer("student", student_id=1)
        from src.api.features import AlertResolveIn
        with self.assertRaises(HTTPException) as ctx:
            success_alert_resolve(AlertResolveIn(title="Predicted High risk", student_id=1), session=session)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_student_cannot_complete_another_task(self):
        _, session = _bearer("student", student_id=1)
        from src.api.features import TaskDoneIn
        with patch("src.api.features.store.select", return_value=[{"id": 9, "student_id": 2, "task": "x", "done": False}]):
            with self.assertRaises(HTTPException) as ctx:
                success_task_done(TaskDoneIn(task_id=9, done=True), session=session)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_missing_task_is_404(self):
        _, session = _bearer("counsellor", staff_id=1)
        from src.api.features import TaskDoneIn
        with patch("src.api.features.store.select", return_value=[]):
            with self.assertRaises(HTTPException) as ctx:
                success_task_done(TaskDoneIn(task_id=404, done=True), session=session)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_staff_search_returns_matching_rows(self):
        _, session = _bearer("counsellor", staff_id=1)
        bundle = {
            "students": [{"student_id": 11, "name": "Dhruv"}, {"student_id": 22, "name": "Ananya"}],
            "enrollments": [],
            "logs": [],
            "academic": [],
            "lms": [],
            "cases": [],
            "recommendations": [],
            "demo": True,
        }
        with patch("src.api.features.load_bundle", return_value=bundle):
            none = success_search(q="zzz-no-match", session=session)
            some = success_search(q="dhr", session=session)
            ident = success_search(q="22", session=session)
        self.assertEqual(none["count"], 0)
        self.assertEqual(some["count"], 1)
        self.assertEqual(some["results"][0]["name"], "Dhruv")
        self.assertEqual(ident["count"], 1)
        self.assertEqual(ident["results"][0]["student_id"], 22)

    def test_non_admin_cannot_invite(self):
        headers, _ = _bearer("counsellor", staff_id=1)
        res = self.client.post(
            "/api/staff/invite",
            headers=headers,
            json={"invited_name": "A", "invited_username": "a", "role": "counsellor"},
        )
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
