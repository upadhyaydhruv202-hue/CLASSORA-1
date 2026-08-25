"""Coherence tests for the prototype demo seed generators.

Does not write to Supabase. Does not train models or touch face/voice pipelines.
"""

from __future__ import annotations

import unittest

from src.success.demo_seed import (
    ASSESSMENTS,
    ATTENDANCE_WEEKS,
    COHORT,
    DEMO_ASSESSMENT_PREFIX,
    DEMO_MARK,
    SEMESTERS,
    SUBJECTS,
    coherence_report,
    expected_attendance_rate,
    is_demo_student_name,
    present_mask,
)
from src.success.demo_seed import _rng


class DemoSeedCatalogTests(unittest.TestCase):
    def test_cohort_size_and_unique_keys(self):
        self.assertGreaterEqual(len(COHORT), 10)
        self.assertLessEqual(len(COHORT), 30)
        keys = [row["key"] for row in COHORT]
        names = [row["name"] for row in COHORT]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(DEMO_MARK in row["name"] for row in COHORT))
        self.assertTrue(all(is_demo_student_name(row["name"]) for row in COHORT))

    def test_personas_cover_jury_paths(self):
        personas = {row["persona"] for row in COHORT}
        self.assertIn("High performer", personas)
        self.assertIn("Average performer", personas)
        self.assertIn("At-risk", personas)
        self.assertIn("High attendance / average academics", personas)
        self.assertIn("High academics / low engagement", personas)
        self.assertIn("Active extracurricular", personas)

    def test_no_contact_pii_fields(self):
        for row in COHORT:
            blob = str(row)
            self.assertNotIn("@", blob)
            self.assertNotIn("phone", blob.lower())
            self.assertTrue(row["name"].endswith(DEMO_MARK))

    def test_assessment_labels_are_mappable(self):
        labels = [f"{DEMO_ASSESSMENT_PREFIX}{name}".lower() for name in ASSESSMENTS]
        self.assertTrue(any("midterm" in label for label in labels))
        self.assertTrue(any("assign" in label for label in labels))
        self.assertTrue(any("quiz" in label for label in labels))
        self.assertTrue(any("project" in label for label in labels))
        self.assertEqual(len(SEMESTERS), 2)
        self.assertEqual(len(SUBJECTS), 4)


class DemoSeedCoherenceTests(unittest.TestCase):
    def test_present_mask_hits_target_rate(self):
        rng = _rng("mask")
        mask = present_mask(40, 95, rng, "stable")
        self.assertEqual(len(mask), 40)
        self.assertEqual(sum(1 for bit in mask if bit), 38)

    def test_generated_records_match_classora_calculators(self):
        for spec in COHORT:
            report = coherence_report(spec)
            expected = expected_attendance_rate(spec)
            self.assertEqual(report["attendance_rate"], expected)
            self.assertAlmostEqual(report["attendance_rate"], spec["attendance_rate"], delta=1.6)
            self.assertEqual(report["attendance_rows"], ATTENDANCE_WEEKS * len(SUBJECTS))
            self.assertEqual(report["academic_rows"], len(SEMESTERS) * len(SUBJECTS) * len(ASSESSMENTS))
            self.assertEqual(report["lms_count"], spec["lms_count"])
            self.assertAlmostEqual(report["academic_avg"], spec["academic_avg"], delta=12)

    def test_profiles_are_not_identical(self):
        aarav = coherence_report(next(row for row in COHORT if row["key"] == "AARAV"))
        kabir = coherence_report(next(row for row in COHORT if row["key"] == "KABIR"))
        meera = coherence_report(next(row for row in COHORT if row["key"] == "MEERA"))
        rohan = coherence_report(next(row for row in COHORT if row["key"] == "ROHAN"))
        self.assertGreater(aarav["attendance_rate"], kabir["attendance_rate"])
        self.assertGreater(aarav["academic_avg"], kabir["academic_avg"])
        self.assertGreater(meera["attendance_rate"], rohan["attendance_rate"] - 5)
        self.assertGreater(rohan["academic_avg"], meera["academic_avg"])
        self.assertGreater(aarav["lms_count"], rohan["lms_count"])

    def test_repeatable_generators(self):
        spec = next(row for row in COHORT if row["key"] == "KABIR")
        first = coherence_report(spec)
        second = coherence_report(spec)
        self.assertEqual(first, second)

    def test_historical_cohort_covers_dropout_statuses(self):
        from src.success.demo_seed import historical_cohort
        rows = historical_cohort()
        self.assertEqual(len(rows), 16)
        statuses = {row["outcome"] for row in rows}
        self.assertGreaterEqual(sum(1 for row in rows if row["outcome"] in ("DROPPED_OUT", "WITHDRAWN", "DISCONTINUED")), 10)
        self.assertIn("GRADUATED", statuses)
        self.assertIn("ACTIVE", statuses)
        self.assertTrue(all("(Demo)" in row["name"] for row in rows))

    def test_staff_catalog_covers_existing_roles(self):
        from src.success.demo_ops import DEMO_PASSWORD, DEMO_TEACHER, STAFF_ACCOUNTS

        roles = {row[1] for row in STAFF_ACCOUNTS}
        usernames = [row[0] for row in STAFF_ACCOUNTS]
        self.assertEqual(len(usernames), len(set(usernames)))
        self.assertTrue(all(name.startswith("DEMO_") for name in usernames))
        self.assertEqual(
            roles,
            {"administrator", "faculty", "counsellor", "mentor"},
        )
        self.assertEqual(DEMO_TEACHER, "DEMO_FACULTY_01")
        self.assertGreaterEqual(len(DEMO_PASSWORD), 8)

    def test_import_fixtures_match_importer(self):
        from pathlib import Path
        from src.success.ops import parse_import_csv
        root = Path(__file__).resolve().parents[1] / "scripts" / "demo_fixtures"
        rows, err = parse_import_csv((root / "academic_valid.csv").read_text(encoding="utf-8"), "academic")
        self.assertEqual(err, "")
        self.assertEqual(len(rows), 2)
        rows, err = parse_import_csv((root / "lms_valid.csv").read_text(encoding="utf-8"), "lms")
        self.assertEqual(err, "")
        self.assertEqual(rows[0]["event_type"], "login")
        rows, err = parse_import_csv((root / "academic_invalid.csv").read_text(encoding="utf-8"), "academic")
        self.assertTrue(err)
        self.assertFalse(rows)


if __name__ == "__main__":
    unittest.main()
