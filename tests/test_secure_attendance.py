"""Secure multi-layer attendance: face match is not present without verification."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import _modules, router
from src.attendance import policy as P
from src.attendance import service as attendance
from src.auth.session import session_payload
from src.auth.tokens import encode_token


class MemoryStore:
    def __init__(self):
        self.tables = {}
        self.seq = {}

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
        session = session_payload(role="student", student={"student_id": kwargs.get("student_id", 1), "name": kwargs.get("name", "Aarav")})
    elif role == "teacher":
        session = session_payload(role="teacher", teacher={"teacher_id": kwargs.get("teacher_id", 1), "username": "tea", "name": "Prof"})
    else:
        session = session_payload(role=role, staff={"staff_id": 1, "username": role, "name": role, "role": role})
    return {"Authorization": f"Bearer {encode_token(session)}"}, session


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class SecureAttendanceTests(unittest.TestCase):
    def setUp(self):
        self.mem = MemoryStore()
        attendance._RATES.clear()
        self.logs = []
        self.patches = [
            patch("src.attendance.service.store", self.mem),
            patch("src.success.notify.store", self.mem),
            patch("src.attendance.service._load_subject", return_value=({"subject_id": 10, "subject_code": "DBMS", "name": "Databases", "section": "A"}, "")),
            patch("src.attendance.service._roster", return_value=[{"student_id": 1, "name": "Aarav"}, {"student_id": 2, "name": "Diya"}]),
            patch("src.attendance.service._write_attendance_log", side_effect=self._log),
        ]
        for item in self.patches:
            item.start()
        self.client = _client()
        self.teacher, _ = _bearer("teacher")
        self.student, _ = _bearer("student", student_id=1)
        self.other, _ = _bearer("student", student_id=2, name="Diya")
        self.admin, _ = _bearer("administrator")

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def _log(self, student_id, subject_id, present=True):
        stamp = datetime.now(timezone.utc).isoformat()
        self.logs.append({"student_id": student_id, "subject_id": subject_id, "is_present": present, "timestamp": stamp})
        return stamp

    def _start(self):
        res = self.client.post("/api/attendance/sessions", headers=self.teacher, json={"subjectId": 10, "lecture": "L1", "durationMinutes": 15})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["session"]

    def _match(self, public_id, student_id=1, confidence=0.96):
        row = attendance._session_by_public(public_id)
        attendance.ingest_face_results(None, row, [{"studentId": student_id, "distance": 0.2, "confidence": confidence, "status": P.FACE_MATCHED}], {1: "Aarav", 2: "Diya"})

    def test_modules(self):
        self.assertIn("Secure Attendance", _modules("teacher"))
        self.assertIn("Verify Attendance", _modules("student"))

    def test_analyze_does_not_mark_present(self):
        sess = self._start()
        self._match(sess["id"])
        live = self.client.get(f"/api/attendance/sessions/{sess['id']}", headers=self.teacher).json()["session"]
        student = next(row for row in live["students"] if row["studentId"] == 1)
        self.assertEqual(student["status"], "VERIFICATION_PENDING")
        self.assertEqual(student["faceStatus"], "FACE_MATCHED")
        self.assertEqual(live["counts"]["present"], 0)
        self.assertEqual(self.logs, [])

    def test_student_qr_confirm_marks_present(self):
        sess = self._start()
        self._match(sess["id"])
        qr = self.client.post("/api/attendance/verification/qr", headers=self.student, json={"sessionId": sess["id"]})
        self.assertEqual(qr.status_code, 200, qr.text)
        token = qr.json()["token"]
        confirmed = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "token": token, "deviceToken": "dev-1"})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["status"], "PRESENT")
        self.assertEqual(len(self.logs), 1)
        self.assertTrue(self.logs[0]["is_present"])

    def test_other_student_cannot_use_token(self):
        sess = self._start()
        self._match(sess["id"], 1)
        self._match(sess["id"], 2)
        token = self.client.post("/api/attendance/verification/qr", headers=self.student, json={"sessionId": sess["id"]}).json()["token"]
        res = self.client.post("/api/attendance/verification/confirm", headers=self.other, json={"sessionId": sess["id"], "token": token, "deviceToken": "dev-2"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "TOKEN_MISMATCH")
        self.assertEqual(self.logs, [])

    def test_reused_token_rejected(self):
        sess = self._start()
        self._match(sess["id"])
        token = self.client.post("/api/attendance/verification/qr", headers=self.student, json={"sessionId": sess["id"]}).json()["token"]
        first = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "token": token, "deviceToken": "dev-1"})
        second = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "token": token, "deviceToken": "dev-1"})
        self.assertEqual(first.status_code, 200)
        self.assertIn(second.status_code, (400, 409))
        self.assertEqual(len([row for row in self.logs if row["is_present"]]), 1)

    def test_expired_token_rejected(self):
        sess = self._start()
        self._match(sess["id"])
        token = self.client.post("/api/attendance/verification/qr", headers=self.student, json={"sessionId": sess["id"]}).json()["token"]
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        for row in self.mem.select("attendance_tokens"):
            if row.get("kind") == "QR" and row.get("status") == "ISSUED":
                row["expires_at"] = past
        res = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "token": token, "deviceToken": "dev-1"})
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json()["detail"], "TOKEN_EXPIRED")
        self.assertEqual(self.logs, [])

    def test_expired_session_rejected(self):
        sess = self._start()
        self._match(sess["id"])
        row = attendance._session_by_public(sess["id"])
        row["expires_at"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        token = self.client.post("/api/attendance/verification/qr", headers=self.student, json={"sessionId": sess["id"]})
        self.assertEqual(token.status_code, 400)
        self.assertEqual(token.json()["detail"], "SESSION_INACTIVE")

    def test_secret_code_and_bruteforce(self):
        attendance.save_settings({"verification_mode": P.MODE_FACE_PLUS_CODE, "device_binding_enabled": False}, {"user_role": "administrator", "staff_data": {"username": "admin"}})
        sess = self._start()
        live = attendance._session_by_public(sess["id"])
        store_row = [row for row in self.mem.select("attendance_sessions") if row.get("public_id") == sess["id"]][0]
        store_row["verification_mode"] = P.MODE_FACE_PLUS_CODE
        self._match(sess["id"])
        issued = self.client.post("/api/attendance/verification/code", headers=self.student, json={"sessionId": sess["id"]})
        self.assertEqual(issued.status_code, 200, issued.text)
        code = issued.json()["code"]
        wrong = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "code": "000000"})
        self.assertEqual(wrong.status_code, 400)
        ok = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess["id"], "code": code})
        self.assertEqual(ok.status_code, 200, ok.text)
        attendance._RATES.clear()
        sess2 = self._start()
        store_row = [row for row in self.mem.select("attendance_sessions") if row.get("public_id") == sess2["id"]][0]
        store_row["verification_mode"] = P.MODE_FACE_PLUS_CODE
        self._match(sess2["id"])
        self.client.post("/api/attendance/verification/code", headers=self.student, json={"sessionId": sess2["id"]})
        limited = None
        for _ in range(10):
            limited = self.client.post("/api/attendance/verification/confirm", headers=self.student, json={"sessionId": sess2["id"], "code": "111111"})
            if limited.status_code == 429:
                break
        self.assertEqual(limited.status_code, 429)

    def test_student_cannot_create_session(self):
        res = self.client.post("/api/attendance/sessions", headers=self.student, json={"subjectId": 10})
        self.assertEqual(res.status_code, 403)

    def test_student_cannot_read_faculty_session(self):
        sess = self._start()
        res = self.client.get(f"/api/attendance/sessions/{sess['id']}", headers=self.student)
        self.assertEqual(res.status_code, 403)

    def test_idor_other_student_pending(self):
        sess = self._start()
        self._match(sess["id"], 1)
        mine = self.client.get("/api/attendance/student/pending", headers=self.student).json()["pending"]
        theirs = self.client.get("/api/attendance/student/pending", headers=self.other).json()["pending"]
        self.assertEqual(len(mine), 1)
        self.assertEqual(len(theirs), 0)

    def test_manual_correction_is_audited(self):
        sess = self._start()
        res = self.client.post(
            f"/api/attendance/sessions/{sess['id']}/correction",
            headers=self.teacher,
            json={"studentId": 2, "decision": "PRESENT", "reason": "Shown in class after the photo"},
        )
        self.assertEqual(res.status_code, 200, res.text)
        audits = [row for row in self.mem.select("attendance_audit") if row.get("action") == "attendance_present"]
        self.assertTrue(audits)
        self.assertEqual(audits[-1]["reason"], "Shown in class after the photo")
        self.assertEqual(len(self.logs), 1)

    def test_face_only_finalize_requires_policy(self):
        sess = self._start()
        self._match(sess["id"])
        blocked = self.client.post(f"/api/attendance/sessions/{sess['id']}/finalize-matched", headers=self.teacher, json={"reason": "photo review"})
        self.assertEqual(blocked.status_code, 403)
        attendance.save_settings({"verification_mode": P.MODE_FACE_ONLY}, {"user_role": "administrator", "staff_data": {"username": "admin"}})
        row = [item for item in self.mem.select("attendance_sessions") if item.get("public_id") == sess["id"]][0]
        row["verification_mode"] = P.MODE_FACE_ONLY
        allowed = self.client.post(f"/api/attendance/sessions/{sess['id']}/finalize-matched", headers=self.teacher, json={"reason": "policy allows faculty finalize"})
        self.assertEqual(allowed.status_code, 200, allowed.text)

    def test_uncertain_face_is_not_assigned(self):
        sess = self._start()
        row = attendance._session_by_public(sess["id"])
        attendance.ingest_face_results(None, row, [{"studentId": None, "distance": 0.6, "confidence": 0.4, "status": P.FACE_UNCERTAIN}])
        live = self.client.get(f"/api/attendance/sessions/{sess['id']}", headers=self.teacher).json()["session"]
        self.assertEqual(live["counts"]["present"], 0)
        self.assertEqual(live["counts"]["pending"], 0)
        self.assertGreaterEqual(live["counts"]["unknown"], 1)

    def test_settings_student_forbidden(self):
        res = self.client.put("/api/attendance/settings", headers=self.student, json={"verification_mode": "FACE_ONLY"})
        self.assertEqual(res.status_code, 403)


if __name__ == "__main__":
    unittest.main()
