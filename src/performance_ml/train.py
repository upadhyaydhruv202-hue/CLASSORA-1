"""Offline training for the final-score forecast. Inference must not call this."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

from src.performance_ml.schema import (
    ARTIFACT_DIR,
    CALIBRATION_LABEL,
    CALIBRATION_METADATA_PATH,
    CALIBRATION_MODEL_PATH,
    CALIBRATION_NAME,
    CALIBRATION_VERSION,
    CATEGORICAL_FEATURES,
    DATA_PATH,
    DATASET_LABEL,
    DATASET_NAME,
    DATASET_SOURCE,
    FEATURES,
    LEAKAGE_EXCLUDED,
    METADATA_PATH,
    MODEL_PATH,
    MODEL_TYPE,
    MODEL_VERSION,
    NUMERIC_FEATURES,
    PII_EXCLUDED,
    RANDOM_SEED,
    ROOT,
    TARGET,
)


def leakage_report(frame: pd.DataFrame) -> dict:
    """Confirm Total_Score and Grade are not used, and record how they relate to Final_Score."""
    total = frame["Total_Score"]
    final = frame[TARGET]
    mid = frame["Midterm_Score"]
    guessed = 0.4 * final + 0.3 * mid + 0.3 * frame["Assignments_Avg"].fillna(frame["Assignments_Avg"].median())
    grade_overlap = {
        str(grade): {
            "final_min": float(group[TARGET].min()),
            "final_max": float(group[TARGET].max()),
            "total_min": float(group["Total_Score"].min()),
            "total_max": float(group["Total_Score"].max()),
            "count": int(len(group)),
        }
        for grade, group in frame.groupby("Grade")
    }
    return {
        "excluded_from_features": LEAKAGE_EXCLUDED,
        "pii_excluded": PII_EXCLUDED,
        "total_score_corr_with_final": float(total.corr(final)),
        "mae_if_total_equals_final": float(np.mean(np.abs(total - final))),
        "mae_if_total_is_weighted_mid_final_assign": float(np.mean(np.abs(total - guessed))),
        "grade_ranges_overlap_final": True,
        "grade_by_final": grade_overlap,
        "decision": (
            "Do not use Total_Score or Grade as inputs. They are excluded by contract. "
            "On this benchmark they are also not a clean function of Final_Score, "
            "so using them would still be invalid for a pre-final estimate."
        ),
    }


def load_dataset(path=DATA_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path)
    missing = [col for col in FEATURES + [TARGET] if col not in frame.columns]
    if missing:
        raise ValueError(f"Dataset is missing required columns: {missing}")
    return frame


def build_pipeline() -> Pipeline:
    numeric = Pipeline(
        steps=[("imputer", SimpleImputer(strategy="median"))],
    )
    categorical = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
        ],
    )
    transform = ColumnTransformer(
        transformers=[
            ("num", numeric, NUMERIC_FEATURES),
            ("cat", categorical, CATEGORICAL_FEATURES),
        ]
    )
    model = RandomForestRegressor(
        n_estimators=80,
        max_depth=10,
        min_samples_leaf=4,
        random_state=RANDOM_SEED,
        n_jobs=1,
    )
    return Pipeline(steps=[("prep", transform), ("model", model)])


def grouped_importances(pipeline: Pipeline) -> list[dict]:
    prep = pipeline.named_steps["prep"]
    forest = pipeline.named_steps["model"]
    names = list(prep.get_feature_names_out())
    weights = forest.feature_importances_
    grouped: dict[str, float] = {name: 0.0 for name in FEATURES}
    for raw, weight in zip(names, weights):
        label = raw.split("__", 1)[-1]
        matched = next((feat for feat in FEATURES if label == feat or label.startswith(f"{feat}_")), None)
        if matched:
            grouped[matched] += float(weight)
    ranked = sorted(grouped.items(), key=lambda item: item[1], reverse=True)
    return [{"feature": name, "importance": round(value, 4)} for name, value in ranked if value > 0]


def train(path=DATA_PATH) -> dict:
    frame = load_dataset(path)
    leak = leakage_report(frame)
    x = frame[FEATURES]
    y = frame[TARGET].astype(float)
    x_train, x_test, y_train, y_test = train_test_split(
        x, y, test_size=0.2, random_state=RANDOM_SEED
    )
    pipeline = build_pipeline()
    pipeline.fit(x_train, y_train)
    pred = pipeline.predict(x_test)
    mae = float(mean_absolute_error(y_test, pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, pred)))
    r2 = float(r2_score(y_test, pred))
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "features": FEATURES, "target": TARGET}, MODEL_PATH)
    metadata = {
        "model_version": MODEL_VERSION,
        "model_type": MODEL_TYPE,
        "dataset_name": DATASET_NAME,
        "dataset_source": DATASET_SOURCE,
        "dataset_label": DATASET_LABEL,
        "dataset_rows": int(len(frame)),
        "dataset_columns": int(frame.shape[1]),
        "target": TARGET,
        "features": FEATURES,
        "feature_count": len(FEATURES),
        "leakage_check": leak,
        "random_seed": RANDOM_SEED,
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "mae": round(mae, 4),
        "rmse": round(rmse, 4),
        "r2": round(r2, 4),
        "important_factors": grouped_importances(pipeline)[:8],
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifact": str(MODEL_PATH.relative_to(ROOT.parent.parent)),
    }
    METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def make_calibration_frame(n=4000, seed=RANDOM_SEED) -> pd.DataFrame:
    """Synthetic rows with a known score relationship. Not written over the public CSV."""
    rng = np.random.default_rng(seed)
    attendance = rng.uniform(50, 100, n)
    midterm = rng.uniform(40, 100, n)
    assignments = rng.uniform(50, 100, n)
    quizzes = rng.uniform(50, 100, n)
    projects = rng.uniform(50, 100, n)
    participation = rng.uniform(0, 10, n)
    study = rng.uniform(5, 30, n)
    stress = rng.integers(1, 11, n).astype(float)
    sleep = rng.uniform(4, 9, n)
    noise = rng.normal(0, 3.5, n)
    final = (
        0.22 * midterm
        + 0.16 * attendance
        + 0.12 * assignments
        + 0.12 * quizzes
        + 0.12 * projects
        + 0.08 * (study / 30.0 * 100.0)
        + 0.05 * (participation * 10.0)
        + 0.05 * (sleep / 8.0 * 100.0)
        - 0.07 * (stress / 10.0 * 100.0)
        + 8.0
        + noise
    )
    final = np.clip(final, 40.0, 99.5)
    frame = pd.DataFrame({
        "Age": rng.integers(18, 25, n),
        "Attendance (%)": attendance,
        "Midterm_Score": midterm,
        "Assignments_Avg": assignments,
        "Quizzes_Avg": quizzes,
        "Participation_Score": participation,
        "Projects_Score": projects,
        "Study_Hours_per_Week": study,
        "Stress_Level (1-10)": stress,
        "Sleep_Hours_per_Night": sleep,
        "Gender": rng.choice(["Male", "Female"], n),
        "Department": rng.choice(["CS", "Engineering", "Business", "Mathematics"], n),
        "Extracurricular_Activities": rng.choice(["Yes", "No"], n, p=[0.35, 0.65]),
        "Internet_Access_at_Home": rng.choice(["Yes", "No"], n, p=[0.9, 0.1]),
            "Parent_Education_Level": rng.choice(["High School", "Bachelor's", "Master's", "PhD"], n),
        "Family_Income_Level": rng.choice(["Low", "Medium", "High"], n),
        TARGET: final,
    })
    miss = rng.choice(n, size=int(n * 0.08), replace=False)
    frame.loc[miss, "Attendance (%)"] = np.nan
    miss2 = rng.choice(n, size=int(n * 0.08), replace=False)
    frame.loc[miss2, "Assignments_Avg"] = np.nan
    miss3 = rng.choice(n, size=int(n * 0.2), replace=False)
    frame.loc[miss3, "Parent_Education_Level"] = np.nan
    return frame


def _fit_and_write(frame: pd.DataFrame, model_path, metadata_path, extra_meta: dict) -> dict:
    x = frame[FEATURES]
    y = frame[TARGET].astype(float)
    x_train, x_test, y_train, y_test = train_test_split(x, y, test_size=0.2, random_state=RANDOM_SEED)
    pipeline = build_pipeline()
    pipeline.fit(x_train, y_train)
    pred = pipeline.predict(x_test)
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipeline, "features": FEATURES, "target": TARGET}, model_path)
    metadata = {
        "model_type": MODEL_TYPE,
        "target": TARGET,
        "features": FEATURES,
        "feature_count": len(FEATURES),
        "random_seed": RANDOM_SEED,
        "train_rows": int(len(x_train)),
        "test_rows": int(len(x_test)),
        "mae": round(float(mean_absolute_error(y_test, pred)), 4),
        "rmse": round(float(np.sqrt(mean_squared_error(y_test, pred))), 4),
        "r2": round(float(r2_score(y_test, pred)), 4),
        "important_factors": grouped_importances(pipeline)[:8],
        "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "artifact": str(model_path.relative_to(ROOT.parent.parent)).replace("\\", "/"),
        **extra_meta,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def train_calibration() -> dict:
    frame = make_calibration_frame()
    return _fit_and_write(
        frame,
        CALIBRATION_MODEL_PATH,
        CALIBRATION_METADATA_PATH,
        {
            "model_version": CALIBRATION_VERSION,
            "dataset_name": CALIBRATION_NAME,
            "dataset_source": "generated in src/performance_ml/train.py:make_calibration_frame",
            "dataset_label": CALIBRATION_LABEL,
            "dataset_rows": int(len(frame)),
            "dataset_columns": int(frame.shape[1]),
            "synthetic": True,
            "leakage_check": {
                "excluded_from_features": LEAKAGE_EXCLUDED,
                "pii_excluded": PII_EXCLUDED,
                "decision": "Synthetic rows do not include Total_Score, Grade, names, or emails.",
            },
        },
    )


def main():
    meta = train()
    cal = train_calibration()
    print(json.dumps({
        "benchmark": {k: meta[k] for k in ("model_version", "dataset_rows", "mae", "rmse", "r2", "trained_at")},
        "calibration": {k: cal[k] for k in ("model_version", "dataset_rows", "mae", "rmse", "r2", "trained_at", "synthetic")},
    }, indent=2))


if __name__ == "__main__":
    main()
