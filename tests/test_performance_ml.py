"""Final-score forecast: leakage contract, isolated inference, RBAC."""

from __future__ import annotations

import json
import unittest
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.features import router
from src.auth.session import session_payload
from src.auth.tokens import encode_token
from src.performance_ml.schema import FEATURES, LEAKAGE_EXCLUDED, METADATA_PATH, PII_EXCLUDED, TARGET
from src.performance_ml.inference import predict_student
from src.performance_ml.mapping import map_student


def _client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _auth(role, **kwargs):
    if role == "student":
        session = session_payload(role="student", student={"student_id": kwargs.get("student_id", 1), "name": "Ada"})
    elif role == "teacher":
        session = session_payload(role="teacher", teacher={"teacher_id": kwargs.get("teacher_id", 1), "username": "tea"})
    else:
        session = session_payload(role=role, staff={"staff_id": 1, "username": role, "role": role})
    return {"Authorization": f"Bearer {encode_token(session)}"}


class PerformanceMlTests(unittest.TestCase):
    def test_metadata_matches_trained_artifact(self):
        meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(meta["dataset_rows"], 5000)
        self.assertEqual(meta["target"], TARGET)
        self.assertEqual(meta["dataset_columns"], 23)
        self.assertNotIn("Total_Score", meta["features"])
        self.assertNotIn("Grade", meta["features"])
        for col in PII_EXCLUDED:
            self.assertNotIn(col, meta["features"])
        self.assertEqual(set(LEAKAGE_EXCLUDED), {"Total_Score", "Grade", TARGET})
        self.assertIsInstance(meta["mae"], float)
        self.assertIsInstance(meta["rmse"], float)
        self.assertIsInstance(meta["r2"], float)

    def test_features_exclude_leakage_and_pii(self):
        for banned in LEAKAGE_EXCLUDED + PII_EXCLUDED:
            self.assertNotIn(banned, FEATURES)

    def test_inference_is_numeric_not_hardcoded(self):
        with patch("src.performance_ml.mapping.predict_one", return_value=None):
            first = predict_student(1, overrides={"Attendance (%)": 60, "Midterm_Score": 55})
            second = predict_student(1, overrides={"Attendance (%)": 95, "Midterm_Score": 90})
        self.assertIsInstance(first["prediction"], float)
        self.assertTrue(0 <= first["prediction"] <= 100)
        self.assertIn(first["performance_band"], ("EXCELLENT", "GOOD", "FAIR", "AT_RISK"))
        self.assertTrue(0 <= second["prediction"] <= 100)

    def test_mapping_does_not_fabricate_missing_fields(self):
        with patch("src.performance_ml.mapping.predict_one", return_value=None):
            with patch("src.performance_ml.mapping.store.select", return_value=[]):
                mapped = map_student(99)
        self.assertTrue(all(value is None for value in mapped["features"].values()))
        self.assertEqual(len(mapped["unavailable"]), len(FEATURES))

    def test_model_endpoint_requires_auth(self):
        client = _client()
        self.assertEqual(client.get("/api/performance/model").status_code, 401)

    def test_model_endpoint_returns_trained_metrics(self):
        client = _client()
        res = client.get("/api/performance/model", headers=_auth("student", student_id=1))
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        meta = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        self.assertEqual(body["mae"], meta["mae"])
        self.assertEqual(body["rmse"], meta["rmse"])
        self.assertEqual(body["r2"], meta["r2"])
        self.assertEqual(body["dataset_rows"], 5000)
        self.assertIn("benchmark", body["dataset_label"].lower())

    def test_student_cannot_predict_another_student(self):
        client = _client()
        res = client.post("/api/performance/predict", headers=_auth("student", student_id=1), json={"student_id": 99})
        self.assertEqual(res.status_code, 403)

    def test_student_predict_uses_own_id(self):
        client = _client()
        with patch("src.performance_ml.mapping.predict_one", return_value={"attendance": {"rate": 80}, "academic": {"avg_score": 72}}):
            with patch("src.performance_ml.mapping.store.select", return_value=[]):
                res = client.post("/api/performance/predict", headers=_auth("student", student_id=1), json={})
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["student_id"], 1)
        self.assertIsInstance(body["prediction"], (int, float))
        self.assertNotIn("First_Name", body)
        self.assertNotIn("Email", json.dumps(body))

    def test_staff_requires_student_id(self):
        client = _client()
        res = client.post("/api/performance/predict", headers=_auth("counsellor"), json={})
        self.assertEqual(res.status_code, 400)

    def test_calibration_model_moves_with_inputs(self):
        from src.performance_ml.schema import CALIBRATION_METADATA_PATH

        meta = json.loads(CALIBRATION_METADATA_PATH.read_text(encoding="utf-8"))
        self.assertTrue(meta.get("synthetic"))
        self.assertGreater(meta["r2"], 0.6)
        self.assertIn("synthetic", meta["dataset_label"].lower())
        low = {
            "Midterm_Score": 45, "Quizzes_Avg": 50, "Projects_Score": 50, "Assignments_Avg": 50,
            "Attendance (%)": 55, "Participation_Score": 3, "Study_Hours_per_Week": 6,
            "Stress_Level (1-10)": 9, "Sleep_Hours_per_Night": 4,
        }
        high = {
            "Midterm_Score": 92, "Quizzes_Avg": 90, "Projects_Score": 88, "Assignments_Avg": 90,
            "Attendance (%)": 96, "Participation_Score": 9, "Study_Hours_per_Week": 24,
            "Stress_Level (1-10)": 3, "Sleep_Hours_per_Night": 8,
        }
        stored = {"attendance": {"rate": 99}, "academic": {"avg_score": 99}}
        with patch("src.performance_ml.mapping.predict_one", return_value=stored):
            with patch("src.performance_ml.mapping.store.select", return_value=[{
                "student_id": 1, "assessment": "Demo · Midterm", "score": 99, "max_score": 100,
            }]):
                low_row = predict_student(1, mode="calibration", overrides=low)
                high_row = predict_student(1, mode="calibration", overrides=high)
        self.assertGreater(high_row["prediction"] - low_row["prediction"], 8)
        self.assertTrue(low_row["synthetic"])
        self.assertEqual(low_row["used_features"]["Attendance (%)"], 55)
        self.assertNotEqual(low_row["used_features"]["Attendance (%)"], 99)
        self.assertEqual(high_row["used_features"]["Midterm_Score"], 92)
        client = _client()
        res = client.post("/api/performance/predict", headers=_auth("student", student_id=1), json={"mode": "calibration", "features": {"Midterm_Score": 80}})
        self.assertEqual(res.status_code, 200, res.text)
        self.assertTrue(res.json().get("synthetic"))
        self.assertIn("used_features", res.json())

    def test_calibration_ignores_stored_records_unless_overridden(self):
        stored = {"attendance": {"rate": 95}, "academic": {"avg_score": 88}}
        with patch("src.performance_ml.mapping.predict_one", return_value=stored):
            with patch("src.performance_ml.mapping.store.select", return_value=[{
                "student_id": 1, "assessment": "Demo · Assignment", "score": 91, "max_score": 100,
            }]):
                mapped = map_student(1, overrides={"Midterm_Score": 40}, include_records=False)
                via_mode = predict_student(1, mode="calibration", overrides={"Attendance (%)": 40, "Midterm_Score": 40})
        self.assertIsNone(mapped["features"]["Attendance (%)"])
        self.assertEqual(mapped["features"]["Midterm_Score"], 40)
        self.assertIsNone(mapped["features"]["Assignments_Avg"])
        self.assertEqual(via_mode["used_features"]["Attendance (%)"], 40)
        self.assertEqual(via_mode["used_features"]["Midterm_Score"], 40)

    def test_dataset_row_matches_direct_model(self):
        import csv
        from pathlib import Path

        import pandas as pd

        from src.performance_ml.inference import _bundle
        from src.performance_ml.schema import DATA_PATH

        with DATA_PATH.open(encoding="utf-8") as handle:
            row = next(csv.DictReader(handle))
        feats = {}
        for key in FEATURES:
            val = row.get(key)
            if val in (None, ""):
                continue
            if key in ("Gender", "Department", "Extracurricular_Activities", "Internet_Access_at_Home", "Parent_Education_Level", "Family_Income_Level"):
                feats[key] = val
            else:
                feats[key] = float(val)
        pipeline, _meta = _bundle("benchmark")
        frame = pd.DataFrame([{name: feats.get(name) for name in FEATURES}], columns=FEATURES)
        direct = round(float(pipeline.predict(frame)[0]), 1)
        with patch("src.performance_ml.mapping.predict_one", return_value=None):
            with patch("src.performance_ml.mapping.store.select", return_value=[]):
                via = predict_student(1, mode="benchmark", overrides=feats)
        self.assertAlmostEqual(via["prediction"], direct, delta=0.15)
        client = _client()
        with patch("src.performance_ml.mapping.predict_one", return_value=None):
            with patch("src.performance_ml.mapping.store.select", return_value=[]):
                res = client.post(
                    "/api/performance/predict",
                    headers=_auth("student", student_id=1),
                    json={"mode": "benchmark", "features": feats},
                )
        self.assertEqual(res.status_code, 200, res.text)
        self.assertAlmostEqual(res.json()["prediction"], direct, delta=0.15)

    def test_predict_failure_is_isolated(self):
        client = _client()
        with patch("src.performance_ml.inference.predict_student", side_effect=RuntimeError("boom")):
            res = client.post("/api/performance/predict", headers=_auth("student", student_id=1), json={})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["detail"], "Prediction temporarily unavailable.")


if __name__ == "__main__":
    unittest.main()
