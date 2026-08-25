"""Load trained final-score artifacts and run on-demand inference."""

from __future__ import annotations

import json
from functools import lru_cache

import pandas as pd

from src.performance_ml.schema import (
    CALIBRATION_METADATA_PATH,
    CALIBRATION_MODEL_PATH,
    FEATURES,
    METADATA_PATH,
    MODEL_PATH,
    MODEL_VERSION,
    TARGET,
)
from src.performance_ml.mapping import map_student

_UNAVAILABLE = "Prediction temporarily unavailable."
MODES = ("benchmark", "calibration")


class ModelUnavailable(RuntimeError):
    pass


def _normalize_mode(mode) -> str:
    value = str(mode or "benchmark").strip().lower()
    if value in ("cal", "demo", "synthetic", "calibration"):
        return "calibration"
    return "benchmark"


def _paths(mode: str):
    if mode == "calibration":
        return CALIBRATION_MODEL_PATH, CALIBRATION_METADATA_PATH
    return MODEL_PATH, METADATA_PATH


def _read_metadata(mode="benchmark") -> dict:
    _model_path, meta_path = _paths(mode)
    if not meta_path.exists():
        raise ModelUnavailable(_UNAVAILABLE)
    return json.loads(meta_path.read_text(encoding="utf-8"))


@lru_cache(maxsize=4)
def _bundle(mode="benchmark"):
    model_path, _meta_path = _paths(mode)
    if not model_path.exists():
        raise ModelUnavailable(_UNAVAILABLE)
    import joblib

    payload = joblib.load(model_path)
    pipeline = payload["pipeline"] if isinstance(payload, dict) else payload
    return pipeline, _read_metadata(mode)


def clear_cache():
    _bundle.cache_clear()


def _pack(meta: dict, mode: str) -> dict:
    return {
        "ready": True,
        "mode": mode,
        "synthetic": bool(meta.get("synthetic")),
        "model_version": meta.get("model_version") or MODEL_VERSION,
        "model_type": meta.get("model_type"),
        "dataset_name": meta.get("dataset_name"),
        "dataset_source": meta.get("dataset_source"),
        "dataset_label": meta.get("dataset_label"),
        "dataset_rows": meta.get("dataset_rows"),
        "dataset_columns": meta.get("dataset_columns"),
        "target": meta.get("target") or TARGET,
        "features": meta.get("features") or FEATURES,
        "feature_count": meta.get("feature_count") or len(FEATURES),
        "mae": meta.get("mae"),
        "rmse": meta.get("rmse"),
        "r2": meta.get("r2"),
        "trained_at": meta.get("trained_at"),
        "important_factors": meta.get("important_factors") or [],
        "leakage_check": {
            "excluded_from_features": (meta.get("leakage_check") or {}).get("excluded_from_features"),
            "decision": (meta.get("leakage_check") or {}).get("decision"),
        },
    }


def model_details(mode=None) -> dict:
    selected = _normalize_mode(mode) if mode else "benchmark"
    try:
        _pipeline, meta = _bundle(selected)
        packed = _pack(meta, selected)
    except Exception:
        packed = _pack(_read_metadata(selected), selected)
        packed["ready"] = True
    try:
        packed["calibration"] = _pack(_read_metadata("calibration"), "calibration")
    except Exception:
        packed["calibration"] = None
    packed["available_modes"] = [name for name in MODES if _paths(name)[0].exists()]
    return packed


def performance_band(score: float) -> str:
    if score >= 85:
        return "EXCELLENT"
    if score >= 70:
        return "GOOD"
    if score >= 55:
        return "FAIR"
    return "AT_RISK"


def predict_student(student_id, session=None, overrides=None, mode="benchmark") -> dict:
    selected = _normalize_mode(mode)
    pipeline, meta = _bundle(selected)
    mapped = map_student(
        student_id,
        session=session,
        overrides=overrides,
        include_records=selected != "calibration",
    )
    frame = pd.DataFrame([mapped["features"]], columns=FEATURES)
    value = float(pipeline.predict(frame)[0])
    value = max(0.0, min(100.0, value))
    synthetic = bool(meta.get("synthetic"))
    return {
        "prediction": round(value, 1),
        "performance_band": performance_band(value),
        "important_factors": meta.get("important_factors") or [],
        "model_version": meta.get("model_version") or MODEL_VERSION,
        "mode": selected,
        "synthetic": synthetic,
        "dataset": meta.get("dataset_name"),
        "dataset_label": meta.get("dataset_label"),
        "target": meta.get("target") or TARGET,
        "mae": meta.get("mae"),
        "rmse": meta.get("rmse"),
        "r2": meta.get("r2"),
        "trained_at": meta.get("trained_at"),
        "student_id": mapped["student_id"],
        "mapped": mapped["mapped"],
        "unavailable": mapped["unavailable"],
        "sources": mapped["sources"],
        "used_features": mapped["features"],
        "disclaimer": (
            "SYNTHETIC demo calibration — not the public benchmark and not institutional records. "
            "On-demand inference. Feature importance is association, not a cause."
            if synthetic
            else (
                "On-demand estimate from the public benchmark model. "
                "Feature importance is association, not a cause. "
                "Missing CLASSORA fields are imputed from training statistics, not invented as live student values."
            )
        ),
    }
