"""CLASSORA Communities: uniqueness, privacy, RBAC, moderation."""

from __future__ import annotations

import threading
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import _modules, router
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.communities import detect
from src.communities import service as communities


class MemoryStore:
    def __init__(self):
        self.tables = {}
        self.seq = {}
        self.lock = threading.Lock()

    def available(self, table):
        return True

    def last_error(self, table):
        return ""

    def insert(self, table, row):
        with self.lock:
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
        with self.lock:
            changed = []
            for row in self.tables.setdefault(table, []):
                if all(row.get(key) == value for key, value in match.items()):
                    row.update(values)
                    changed.append(row)
            return changed

    def delete(self, table, **eq):
        with self.lock:
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
        session = session_payload(
            role="student",
            student={"student_id": kwargs.get("student_id", 1), "name": kwargs.get("name", "Aarav")},
        )
    elif role == "merchant":
        session = session_payload(role="merchant", merchant={"merchant_id": 1, "name": "Canteen"})
    else:
        session = session_payload(
            role=role,
            staff={"staff_id": kwargs.get("staff_id", 1), "username": kwargs.get("username", role), "name": role, "role": role},
        )
    return {"Authorization": f"Bearer {encode_token(session)}"}


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class DetectTests(unittest.TestCase):
    def test_club_suffix_is_near_duplicate(self):
        score = detect.similarity("Football", "Football Club")
        self.assertGreaterEqual(score, 0.92)
        self.assertEqual(detect.classify_match(score), "NEAR_DUPLICATE")

    def test_ai_alias(self):
        score = detect.similarity("Artificial Intelligence", "AI Club")
        self.assertGreaterEqual(score, 0.92)

    def test_specialized_is_not_auto_merged(self):
        score = detect.similarity("Football", "Football Analytics")
        self.assertLess(score, 0.92)
        self.assertEqual(detect.classify_match(score), "POTENTIAL_DUPLICATE")


class CommunityApiTests(unittest.TestCase):
    def setUp(self):
        self.mem = MemoryStore()
        communities._RATES.clear()
        self.patches = [
            patch("src.communities.service.store", self.mem),
            patch("src.success.notify.store", self.mem),
        ]
        for item in self.patches:
            item.start()
        communities.ensure_seed()
        self.client = _client()
        self.student = _bearer("student", student_id=1, name="Aarav")
        self.student2 = _bearer("student", student_id=2, name="Diya")
        self.admin = _bearer("administrator", staff_id=9, username="admin1")
        self.merchant = _bearer("merchant")

    def tearDown(self):
        for item in self.patches:
            item.stop()

    def _request(self, headers, name, category="SPORTS", **extra):
        return self.client.post("/api/communities/requests", headers=headers, json={
            "name": name,
            "category": category,
            "description": f"{name} for students who want to practice and collaborate.",
            "purpose": "Practice and peer learning",
            "reason": extra.pop("reason", f"There is no {name} community."),
            **extra,
        })

    def _approve_named(self, name, category="SPORTS"):
        created = self._request(self.student, name, category)
        self.assertEqual(created.status_code, 200, created.text)
        req_id = created.json()["id"]
        approved = self.client.post(f"/api/communities/requests/{req_id}/review", headers=self.admin, json={"decision": "APPROVE"})
        self.assertEqual(approved.status_code, 200, approved.text)
        return approved.json()["community"]

    def test_modules(self):
        self.assertIn("Communities", _modules("student"))
        self.assertIn("Communities", _modules("administrator"))
        self.assertNotIn("Communities", _modules("merchant"))
        self.assertNotIn("Communities", _modules("teacher"))

    def test_request_and_approve_new_community(self):
        created = self._request(self.student, "Robotics", "TECHNICAL")
        self.assertEqual(created.status_code, 200, created.text)
        self.assertEqual(created.json()["status"], "PENDING")
        listed = self.client.get("/api/communities", headers=self.student2)
        self.assertFalse(any(row["name"] == "Robotics" for row in listed.json()["communities"]))
        approved = self.client.post(
            f"/api/communities/requests/{created.json()['id']}/review",
            headers=self.admin,
            json={"decision": "APPROVE"},
        )
        self.assertEqual(approved.status_code, 200, approved.text)
        self.assertEqual(approved.json()["community"]["status"], "ACTIVE")
        found = self.client.get("/api/communities?q=Robotics", headers=self.student2)
        self.assertTrue(any(row["name"] == "Robotics" for row in found.json()["communities"]))

    def test_duplicate_football_is_flagged(self):
        self._approve_named("Football")
        again = self._request(self.student2, "Football Club")
        self.assertEqual(again.status_code, 200, again.text)
        body = again.json()
        self.assertTrue(body.get("blocked") or body.get("matches"))
        names = [row["name"] for row in body.get("matches") or []]
        self.assertIn("Football", names)
        forced = self._request(self.student2, "Football Club", continueDespiteDuplicates=True)
        self.assertEqual(forced.status_code, 200, forced.text)
        self.assertTrue(forced.json().get("duplicateFlag"))
        self.assertEqual(forced.json()["status"], "PENDING")

    def test_ai_alias_duplicate(self):
        self._approve_named("Artificial Intelligence", "TECHNICAL")
        similar = self.client.post("/api/communities/similar", headers=self.student2, json={
            "name": "AI Club",
            "category": "TECHNICAL",
            "description": "Students interested in AI.",
        })
        self.assertEqual(similar.status_code, 200, similar.text)
        self.assertTrue(similar.json()["hasNearDuplicate"])

    def test_privacy_hides_name_from_api(self):
        community = self._approve_named("Cricket")
        self.client.post(f"/api/communities/{community['id']}/join", headers=self.student2)
        post = self.client.post(f"/api/communities/{community['id']}/posts", headers=self.student, json={"content": "Practice tomorrow?"})
        self.assertEqual(post.status_code, 200, post.text)
        self.assertNotIn("name", post.json().get("author") or {})
        self.assertEqual(post.json()["author"]["studentId"], 1)
        blob = post.text
        self.assertNotIn("Aarav", blob)
        members = self.client.get(f"/api/communities/{community['id']}/members", headers=self.student2)
        for row in members.json()["members"]:
            if row["studentId"] == 1:
                self.assertNotIn("name", row)
                self.assertNotIn("Aarav", str(row))
        self.client.put("/api/communities/privacy", headers=self.student, json={"showName": True, "displayName": "Aarav"})
        after = self.client.get(f"/api/communities/{community['id']}/posts", headers=self.student2)
        author = after.json()["posts"][0]["author"]
        self.assertEqual(author.get("name"), "Aarav")
        self.assertNotIn("email", author)
        self.assertNotIn("phone", author)

    def test_student_cannot_approve_or_suspend(self):
        created = self._request(self.student, "Music", "MUSIC")
        forbidden = self.client.post(
            f"/api/communities/requests/{created.json()['id']}/review",
            headers=self.student2,
            json={"decision": "APPROVE"},
        )
        self.assertEqual(forbidden.status_code, 403)
        community = self._approve_named("Dance", "ACTIVITIES")
        suspend = self.client.post(f"/api/communities/{community['id']}/status", headers=self.student2, json={"status": "SUSPENDED"})
        self.assertEqual(suspend.status_code, 403)

    def test_moderation_and_suspension(self):
        community = self._approve_named("Photography", "ARTS")
        self.client.post(f"/api/communities/{community['id']}/join", headers=self.student2)
        posted = self.client.post(f"/api/communities/{community['id']}/posts", headers=self.student2, json={"content": "Spam exam answers here"})
        reported = self.client.post("/api/communities/reports", headers=self.student, json={
            "communityId": community["id"],
            "targetType": "POST",
            "postId": posted.json()["id"],
            "reason": "Academic misconduct",
            "description": "Looks like cheating.",
        })
        self.assertEqual(reported.status_code, 200, reported.text)
        reports = self.client.get("/api/community-reports", headers=self.admin)
        self.assertEqual(reports.status_code, 200, reports.text)
        report_id = reports.json()["reports"][0]["id"]
        resolved = self.client.post(f"/api/communities/reports/{report_id}/resolve", headers=self.admin, json={"action": "CONTENT_REMOVED"})
        self.assertEqual(resolved.status_code, 200, resolved.text)
        feed = self.client.get(f"/api/communities/{community['id']}/posts", headers=self.student)
        self.assertEqual(feed.json()["posts"], [])
        logs = [row for row in self.mem.select("community_moderation") if row.get("action") == "CONTENT_REMOVED"]
        self.assertTrue(logs)
        self.client.post(f"/api/communities/{community['id']}/status", headers=self.admin, json={"status": "SUSPENDED", "reason": "Misuse"})
        blocked = self.client.post(f"/api/communities/{community['id']}/posts", headers=self.student, json={"content": "Still posting"})
        self.assertEqual(blocked.status_code, 403)

    def test_join_leave_and_events(self):
        community = self._approve_named("Chess")
        joined = self.client.post(f"/api/communities/{community['id']}/join", headers=self.student2)
        self.assertEqual(joined.status_code, 200, joined.text)
        event = self.client.post(f"/api/communities/{community['id']}/events", headers=self.student, json={
            "title": "Chess practice",
            "description": "Board games room",
            "startAt": "2026-08-24 17:00",
            "location": "Sports hall",
        })
        self.assertEqual(event.status_code, 200, event.text)
        reg = self.client.post(f"/api/communities/{community['id']}/events/{event.json()['id']}/register", headers=self.student2)
        self.assertEqual(reg.status_code, 200, reg.text)
        left = self.client.delete(f"/api/communities/{community['id']}/leave", headers=self.student2)
        self.assertEqual(left.status_code, 200)
        listed = self.client.get("/api/communities?mine=true", headers=self.student2)
        self.assertFalse(any(row["id"] == community["id"] for row in listed.json()["communities"]))

    def test_privacy_settings_idor(self):
        stolen = self.client.put("/api/communities/privacy", headers=self.student2, json={"studentId": 1, "showName": True, "displayName": "Hacked"})
        self.assertEqual(stolen.status_code, 403)
        own = self.client.put("/api/communities/privacy", headers=self.student2, json={"showName": True, "displayName": "Diya"})
        self.assertEqual(own.status_code, 200)
        self.assertEqual(own.json()["displayName"], "Diya")

    def test_merchant_blocked(self):
        self.assertEqual(self.client.get("/api/communities/overview").status_code, 401)
        self.assertEqual(self.client.get("/api/communities/overview", headers=self.merchant).status_code, 403)

    def test_xss_stripped_from_posts(self):
        community = self._approve_named("Theatre", "ARTS")
        posted = self.client.post(f"/api/communities/{community['id']}/posts", headers=self.student, json={
            "content": "<script>alert(1)</script>Hello javascript:alert(1)",
        })
        self.assertEqual(posted.status_code, 200, posted.text)
        self.assertNotIn("<script>", posted.json()["content"])
        self.assertNotIn("javascript:", posted.json()["content"])


if __name__ == "__main__":
    unittest.main()
