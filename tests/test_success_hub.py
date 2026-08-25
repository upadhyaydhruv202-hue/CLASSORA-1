"""Reports, search, import, and staff-invite activation for existing Success Hub modules."""

import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from src.database.db import hash_pass
from src.success.ops import build_report, parse_import_csv, report_rows, search_profiles, settings_payload
from src.success.staff_auth import activate_staff


class ReportSearchImportTests(unittest.TestCase):
    def test_report_uses_real_profile_counts(self):
        profiles = [
            {"student_id": 1, "name": "A", "prediction": {"category": "High", "score": 80}, "attendance": {"rate": 60}},
            {"student_id": 2, "name": "B", "prediction": {"category": "Low", "score": 20}, "attendance": {"rate": 90}},
        ]
        report = build_report(
            profiles,
            cases=[{"status": "open"}, {"status": "closed"}],
            alerts=[{"title": "x"}],
            appointments=[{"status": "requested"}, {"status": "connected"}],
            academic=[{}, {}],
            lms=[{}],
            outcomes=[{}],
        )
        self.assertEqual(report["student_count"], 2)
        self.assertEqual(report["high_critical"], 1)
        self.assertEqual(report["avg_attendance"], 75.0)
        self.assertEqual(report["open_cases"], 1)
        self.assertEqual(report["closed_cases"], 1)
        self.assertEqual(report["bands"]["High"], 1)
        self.assertEqual(report["bands"]["Low"], 1)
        self.assertEqual(len(report_rows(profiles)), 2)

    def test_search_matches_name_id_and_standing(self):
        profiles = [
            {"student_id": 11, "name": "Dhruv", "prediction": {"category": "Critical"}},
            {"student_id": 22, "name": "Ananya", "prediction": {"category": "Low"}},
        ]
        self.assertEqual(len(search_profiles(profiles, "dhr")), 1)
        self.assertEqual(len(search_profiles(profiles, "22")), 1)
        self.assertEqual(len(search_profiles(profiles, "critical")), 1)
        self.assertEqual(len(search_profiles(profiles, "")), 2)

    def test_academic_csv_parse(self):
        text = "student_id,assessment,score,max_score,gpa\n7,Midterm,18,20,8.5\n"
        rows, err = parse_import_csv(text, "academic")
        self.assertEqual(err, "")
        self.assertEqual(rows[0]["student_id"], 7)
        self.assertEqual(rows[0]["assessment"], "Midterm")
        self.assertEqual(rows[0]["score"], 18.0)

    def test_lms_csv_parse_and_reject_empty(self):
        text = "student_id,event_type,course_code\n3,login,CS101\n"
        rows, err = parse_import_csv(text, "lms")
        self.assertEqual(err, "")
        self.assertEqual(rows[0]["event_type"], "login")
        empty, empty_err = parse_import_csv("", "academic")
        self.assertEqual(empty, [])
        self.assertTrue(empty_err)

    def test_settings_payload(self):
        out = settings_payload({"institution_name": " NIT ", "note": "hello"})
        self.assertEqual(out["institution_name"], "NIT")
        self.assertEqual(out["support_note"], "hello")


class InstitutionSettingsPersistenceTests(unittest.TestCase):
    def test_hub_settings_prefers_id_1(self):
        from src.api.features import _hub_settings
        rows = [
            {"id": 2, "settings": {"institution_name": "Wrong"}},
            {"id": 1, "settings": {"institution_name": "NIT", "support_note": "hi"}},
        ]
        with patch("src.api.features.store.select", return_value=rows):
            self.assertEqual(_hub_settings()["institution_name"], "NIT")
            self.assertEqual(_hub_settings()["support_note"], "hi")

    def test_hub_settings_reads_flat_columns(self):
        from src.api.features import _hub_settings
        with patch("src.api.features.store.select", return_value=[{
            "id": 1,
            "institution_name": "Flat College",
            "support_note": "note",
        }]):
            self.assertEqual(_hub_settings()["institution_name"], "Flat College")

    def test_save_then_get_roundtrip(self):
        from src.api.features import SettingsIn, success_settings_get, success_settings_save
        from src.auth.session import session_payload

        db = {"rows": []}

        def select(table, **eq):
            rows = list(db["rows"])
            if "id" in eq:
                return [row for row in rows if row.get("id") == eq["id"]]
            return rows

        def update(table, match, values):
            changed = []
            for row in db["rows"]:
                if row.get("id") == match.get("id"):
                    row.update(values)
                    changed.append(dict(row))
            return changed

        def insert(table, row):
            db["rows"].append(dict(row))
            return [dict(row)]

        session = session_payload(
            role="administrator",
            staff={"staff_id": 1, "username": "admin", "name": "Admin", "role": "administrator"},
        )
        with patch("src.api.features.store.select", side_effect=select), \
             patch("src.api.features.store.update", side_effect=update), \
             patch("src.api.features.store.insert", side_effect=insert):
            saved = success_settings_save(
                SettingsIn(institution_name="Persist Me", support_note="keep"),
                session=session,
            )
            self.assertEqual(saved["settings"]["institution_name"], "Persist Me")
            self.assertEqual(db["rows"][0]["settings"]["institution_name"], "Persist Me")
            got = success_settings_get(session=session)
            self.assertEqual(got["settings"]["institution_name"], "Persist Me")
            self.assertEqual(got["settings"]["support_note"], "keep")

    def test_save_persists_when_update_returns_no_representation(self):
        from src.api.features import SettingsIn, success_settings_get, success_settings_save
        from src.auth.session import session_payload

        db = {"rows": [{"id": 1, "settings": {}}]}

        def select(table, **eq):
            rows = list(db["rows"])
            if "id" in eq:
                return [row for row in rows if row.get("id") == eq["id"]]
            return rows

        def update(table, match, values):
            for row in db["rows"]:
                if row.get("id") == match.get("id"):
                    row.update(values)
            return []

        session = session_payload(
            role="administrator",
            staff={"staff_id": 1, "username": "admin", "name": "Admin", "role": "administrator"},
        )
        with patch("src.api.features.store.select", side_effect=select), \
             patch("src.api.features.store.update", side_effect=update):
            saved = success_settings_save(
                SettingsIn(institution_name="After Minimal Return", support_note=""),
                session=session,
            )
            self.assertEqual(saved["settings"]["institution_name"], "After Minimal Return")
            got = success_settings_get(session=session)
            self.assertEqual(got["settings"]["institution_name"], "After Minimal Return")


class StaffActivateTests(unittest.TestCase):
    def test_rejects_invalid_token(self):
        with patch("src.success.staff_auth.store.select", return_value=[]):
            staff, msg = activate_staff("alex", "nope", "Password1!", "Password1!")
        self.assertIsNone(staff)
        self.assertIn("invalid", msg.lower())

    def test_activates_unused_invite(self):
        token = "invite-code-123"
        invite = {
            "invite_id": 9,
            "invited_name": "Alex",
            "invited_username": "alex",
            "assigned_role": "counsellor",
            "token_hash": hash_pass(token),
            "used_at": None,
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=2)).isoformat(),
        }
        created = {"staff_id": 4, "username": "alex", "name": "Alex", "role": "counsellor"}
        with patch("src.success.staff_auth.store.select", return_value=[invite]), \
             patch("src.success.staff_auth.store.update", return_value=[invite]), \
             patch("src.success.staff_auth.is_supabase_configured", create=True), \
             patch("src.database.config.is_supabase_configured", return_value=True), \
             patch("src.success.staff_auth.create_staff", return_value=([created], "ok")), \
             patch("src.success.staff_auth.log_auth_event"):
            staff, msg = activate_staff("alex", token, "Password1!", "Password1!")
        self.assertEqual(staff["username"], "alex")
        self.assertIn("activated", msg.lower())


if __name__ == "__main__":
    unittest.main()
