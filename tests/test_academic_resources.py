"""Academic Resource Hub: URL safety, RBAC, search, filters, duplicates."""

from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.academic import service as academic
from src.api.features import _modules, router
from src.auth.session import session_payload
from src.auth.tokens import encode_token


class MemoryStore:
    def __init__(self):
        self.tables = {}
        self.seq = {}
        self.errors = {}

    def available(self, table):
        return True

    def last_error(self, table):
        return self.errors.get(table, "")

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


class UrlValidationTests(unittest.TestCase):
    def test_empty_rejected(self):
        url, err = academic.normalize_url("   ")
        self.assertIsNone(url)
        self.assertIn("required", err.lower())

    def test_javascript_rejected(self):
        url, err = academic.normalize_url("javascript:alert(1)")
        self.assertIsNone(url)
        self.assertIn("not allowed", err.lower())

    def test_http_rejected(self):
        url, err = academic.normalize_url("http://thebrainspot.org/notes.pdf")
        self.assertIsNone(url)
        self.assertIn("https", err.lower())

    def test_data_rejected(self):
        url, err = academic.normalize_url("data:text/html,hi")
        self.assertIsNone(url)
        self.assertIn("not allowed", err.lower())

    def test_https_normalized(self):
        url, err = academic.normalize_url("  https://TheBrainSpot.org/notes.pdf?x=1#frag  ")
        self.assertIsNone(err)
        self.assertTrue(url.startswith("https://thebrainspot.org/notes.pdf"))
        self.assertNotIn("#", url)

    def test_pdf_format_inferred(self):
        self.assertEqual(academic.infer_format("https://example.com/os.pdf"), "PDF")
        self.assertEqual(academic.infer_format("https://thebrainspot.org/2nd-year/"), "WEBPAGE")

    def test_year_and_semester_aliases(self):
        self.assertEqual(academic.resolve_year_id("2"), "YEAR_2")
        self.assertEqual(academic.resolve_semester_id("4"), "SEM_4")
        self.assertEqual(academic.resolve_semester_id("Semester 4"), "SEM_4")


class AcademicApiTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.patcher = patch("src.academic.service.store", self.store)
        self.patcher.start()
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)
        self.admin, _ = _bearer("administrator")
        self.student, _ = _bearer("student", student_id=18)
        self.teacher, _ = _bearer("teacher")
        self.counsellor, _ = _bearer("counsellor")

    def tearDown(self):
        self.patcher.stop()

    def _seed_subject_and_resource(self, title="Operating Systems Complete Notes", url="https://thebrainspot.org/os-notes.pdf"):
        catalog = self.client.get("/api/academic-resources/catalog", headers=self.admin).json()
        types = catalog["types"]
        sources = catalog["sources"]
        notes = next(row for row in types if row["code"] == "NOTES")
        source = next(row for row in sources if row["code"] == "brainspot_y2")
        subject = self.client.post("/api/academic-subjects", headers=self.admin, json={
            "name": "Operating Systems",
            "code": "OS",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
        }).json()["subject"]
        extra = self.client.post("/api/academic-subjects", headers=self.admin, json={
            "name": "Database Management System",
            "code": "DBMS",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
        }).json()["subject"]
        created = self.client.post("/api/academic-resources", headers=self.admin, json={
            "title": title,
            "description": "Senior OS notes",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
            "subject_id": subject["id"],
            "resource_type_id": notes["id"],
            "source_id": source["id"],
            "original_url": url,
            "tags": "os, notes",
        })
        self.assertEqual(created.status_code, 200, created.text)
        dbms = self.client.post("/api/academic-resources", headers=self.admin, json={
            "title": "DBMS Question Bank",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
            "subject_id": extra["id"],
            "resource_type_id": next(row["id"] for row in types if row["code"] == "QUESTION_BANK"),
            "source_id": source["id"],
            "original_url": "https://thebrainspot.org/dbms-qb.pdf",
        })
        self.assertEqual(dbms.status_code, 200, dbms.text)
        return created.json()["resource"], subject, notes, source

    def test_requires_auth(self):
        self.assertEqual(self.client.get("/api/academic-resources").status_code, 401)
        self.assertEqual(self.client.get("/api/academic-resources/catalog").status_code, 401)

    def test_student_cannot_create(self):
        res = self.client.post("/api/academic-resources", headers=self.student, json={
            "title": "Hack",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
            "original_url": "https://example.com/x.pdf",
        })
        self.assertEqual(res.status_code, 403)

    def test_teacher_cannot_create_or_manage(self):
        res = self.client.post("/api/academic-resources", headers=self.teacher, json={"title": "No", "original_url": "https://example.com/x.pdf"})
        self.assertEqual(res.status_code, 403)
        res = self.client.get("/api/academic-resource-reports", headers=self.teacher)
        self.assertEqual(res.status_code, 403)

    def test_counsellor_cannot_manage(self):
        res = self.client.post("/api/academic-subjects", headers=self.counsellor, json={
            "name": "OS", "year_id": "YEAR_2", "semester_id": "SEM_4",
        })
        self.assertEqual(res.status_code, 403)

    def test_catalog_seeds_sources_not_fake_resources(self):
        res = self.client.get("/api/academic-resources/catalog", headers=self.student)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["installed"])
        names = [row["name"] for row in data["sources"]]
        urls = [row["website_url"] for row in data["sources"]]
        self.assertIn("The Brain Spot — Information Technology", names)
        self.assertIn("https://thebrainspot.org/information-technology/", urls)
        self.assertIn("https://thebrainspot.org/2nd-year/", urls)
        self.assertIn("https://thebrainspot.org/3rd-year/", urls)
        self.assertIn("https://ldrp.bhavsarneev.de/index.php", urls)
        self.assertIn("https://www.collegpt.com/courses", urls)
        listed = self.client.get("/api/academic-resources", headers=self.student).json()
        self.assertEqual(listed["total"], 0)
        self.assertEqual(listed["items"], [])

    def test_admin_create_and_student_open_original_url(self):
        resource, *_ = self._seed_subject_and_resource()
        self.assertEqual(resource["originalUrl"], "https://thebrainspot.org/os-notes.pdf")
        self.assertEqual(resource["resourceFormat"], "PDF")
        self.assertTrue(str(resource["sourceName"]).startswith("The Brain Spot"))
        listed = self.client.get("/api/academic-resources?year=2&semester=4&type=notes", headers=self.student).json()
        self.assertEqual(listed["total"], 1)
        self.assertEqual(listed["items"][0]["originalUrl"], "https://thebrainspot.org/os-notes.pdf")
        one = self.client.get(f"/api/academic-resources/{resource['id']}", headers=self.student)
        self.assertEqual(one.status_code, 200)
        self.assertEqual(one.json()["originalUrl"], resource["originalUrl"])

    def test_search_is_case_insensitive(self):
        self._seed_subject_and_resource()
        found = self.client.get("/api/academic-resources?search=dbms", headers=self.student).json()
        titles = [row["title"] for row in found["items"]]
        self.assertTrue(any("DBMS" in title for title in titles))
        none = self.client.get("/api/academic-resources?search=zzzz-no-match", headers=self.student).json()
        self.assertEqual(none["total"], 0)

    def test_filters_and_pagination(self):
        self._seed_subject_and_resource()
        year1 = self.client.get("/api/academic-resources?year=YEAR_1", headers=self.student).json()
        self.assertEqual(year1["total"], 0)
        page = self.client.get("/api/academic-resources?limit=1&page=1&sort=alpha", headers=self.student).json()
        self.assertEqual(page["limit"], 1)
        self.assertEqual(page["total"], 2)
        self.assertEqual(len(page["items"]), 1)

    def test_duplicate_url_same_subject_type_rejected(self):
        resource, subject, notes, source = self._seed_subject_and_resource()
        again = self.client.post("/api/academic-resources", headers=self.admin, json={
            "title": "Copy",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
            "subject_id": subject["id"],
            "resource_type_id": notes["id"],
            "source_id": source["id"],
            "original_url": resource["originalUrl"],
        })
        self.assertEqual(again.status_code, 400)
        self.assertIn("already listed", again.json()["detail"].lower())

    def test_unsafe_url_rejected_on_create(self):
        catalog = self.client.get("/api/academic-resources/catalog", headers=self.admin).json()
        subject = self.client.post("/api/academic-subjects", headers=self.admin, json={
            "name": "DSA", "year_id": "YEAR_2", "semester_id": "SEM_3",
        }).json()["subject"]
        res = self.client.post("/api/academic-resources", headers=self.admin, json={
            "title": "Bad",
            "year_id": "YEAR_2",
            "semester_id": "SEM_3",
            "subject_id": subject["id"],
            "resource_type_id": catalog["types"][0]["id"],
            "source_id": catalog["sources"][0]["id"],
            "original_url": "javascript:alert(1)",
        })
        self.assertEqual(res.status_code, 400)

    def test_cross_semester_subject_rejected(self):
        catalog = self.client.get("/api/academic-resources/catalog", headers=self.admin).json()
        subject = self.client.post("/api/academic-subjects", headers=self.admin, json={
            "name": "COA", "year_id": "YEAR_2", "semester_id": "SEM_3",
        }).json()["subject"]
        res = self.client.post("/api/academic-resources", headers=self.admin, json={
            "title": "Wrong semester",
            "year_id": "YEAR_2",
            "semester_id": "SEM_4",
            "subject_id": subject["id"],
            "resource_type_id": catalog["types"][0]["id"],
            "source_id": catalog["sources"][0]["id"],
            "original_url": "https://thebrainspot.org/coa.pdf",
        })
        self.assertEqual(res.status_code, 400)

    def test_inactive_hidden_from_students(self):
        resource, *_ = self._seed_subject_and_resource()
        gone = self.client.delete(f"/api/academic-resources/{resource['id']}", headers=self.admin)
        self.assertEqual(gone.status_code, 200)
        listed = self.client.get("/api/academic-resources", headers=self.student).json()
        ids = [row["id"] for row in listed["items"]]
        self.assertNotIn(resource["id"], ids)
        admin_list = self.client.get("/api/academic-resources", headers=self.admin).json()
        self.assertTrue(any(row["id"] == resource["id"] for row in admin_list["items"]))

    def test_student_can_report_once(self):
        resource, *_ = self._seed_subject_and_resource()
        first = self.client.post(
            f"/api/academic-resources/{resource['id']}/report",
            headers=self.student,
            json={"reason": "Resource link is not working"},
        )
        self.assertEqual(first.status_code, 200)
        second = self.client.post(
            f"/api/academic-resources/{resource['id']}/report",
            headers=self.student,
            json={"reason": "Resource link is not working"},
        )
        self.assertEqual(second.status_code, 400)
        reports = self.client.get("/api/academic-resource-reports", headers=self.admin).json()["reports"]
        self.assertEqual(len(reports), 1)
        reviewed = self.client.post(
            f"/api/academic-resource-reports/{reports[0]['id']}/review",
            headers=self.admin,
            json={"decision": "RESOLVED"},
        )
        self.assertEqual(reviewed.status_code, 200)

    def test_modules_include_academic_resources(self):
        self.assertIn("Academic Resources", _modules("student"))
        self.assertIn("Academic Resources", _modules("administrator"))
        self.assertNotIn("Academic Resources", _modules("counsellor"))
        self.assertNotIn("Academic Resources", _modules("teacher"))


if __name__ == "__main__":
    unittest.main()
