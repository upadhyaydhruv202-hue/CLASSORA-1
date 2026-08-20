"""Face identity — same dlib 128-d pipeline as the original Streamlit app.

Match is nearest-neighbor L2 (face_recognition.compare_faces / 0.6), not SVM.
SVM broke FaceID when only one student was enrolled and often picked the
wrong person even with two or more.
"""
import json

import dlib
import numpy as np
import face_recognition_models
from PIL import Image

from src.database.db import get_all_students

_dlib_models = None
_trained_model = None

FACE_SIZE = 128
MATCH_THRESHOLD = 0.6


def _shrink(image_np, max_side=640):
    image = Image.fromarray(image_np)
    image.thumbnail((max_side, max_side))
    return np.array(image)


def as_face_vector(value):
    if value is None:
        return None
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            return None
    try:
        arr = np.asarray(value, dtype=np.float64).reshape(-1)
    except Exception:
        return None
    if arr.size != FACE_SIZE:
        return None
    return arr


def load_dlib_models():
    global _dlib_models
    if _dlib_models is None:
        detector = dlib.get_frontal_face_detector()
        sp = dlib.shape_predictor(face_recognition_models.pose_predictor_model_location())
        facerec = dlib.face_recognition_model_v1(face_recognition_models.face_recognition_model_location())
        _dlib_models = (detector, sp, facerec)
    return _dlib_models


def get_face_embeddings(image_np, max_side=640, upsample=1):
    """HOG detector + 128-d descriptor. upsample=1 matches face_recognition defaults."""
    detector, sp, facerec = load_dlib_models()
    image_np = _shrink(image_np, max_side=max_side)
    faces = detector(image_np, upsample)
    encodings = []
    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1)
        encodings.append(np.array(face_descriptor, dtype=np.float64))
    return encodings


def known_face_rows(rows):
    known = []
    for row in rows or []:
        vec = as_face_vector(row.get("face_embedding"))
        if vec is None:
            continue
        try:
            sid = int(row["student_id"])
        except (KeyError, TypeError, ValueError):
            continue
        known.append((sid, vec))
    return known


def match_faces(image_np, known_rows, threshold=MATCH_THRESHOLD, max_side=640, upsample=1):
    """Return ({student_id: True, ...}, faces_found) using L2 ≤ 0.6 like Streamlit."""
    encodings = get_face_embeddings(image_np, max_side=max_side, upsample=upsample)
    known = known_face_rows(known_rows)
    detected = {}
    for encoding in encodings:
        best_id = None
        best = 999.0
        for sid, vec in known:
            score = float(np.linalg.norm(vec - encoding))
            if score < best:
                best = score
                best_id = sid
        if best_id is not None and best <= threshold:
            detected[best_id] = True
    return detected, len(encodings)


def get_trained_model():
    """Kept for startup preload. Matching no longer depends on SVM."""
    global _trained_model
    if _trained_model is not None:
        return _trained_model
    student_db = get_all_students("student_id, face_embedding") or []
    known = known_face_rows(student_db)
    if not known:
        return None
    X = [vec for _, vec in known]
    y = [sid for sid, _ in known]
    _trained_model = {"clf": None, "X": X, "y": y}
    return _trained_model


def invalidate_classifier():
    global _trained_model
    _trained_model = None


def train_classifier():
    invalidate_classifier()
    return bool(get_trained_model())


def predict_attendance(class_image_np, known_students=None):
    if known_students is None:
        known_students = get_all_students("student_id, face_embedding") or []
    detected, num_faces = match_faces(
        class_image_np,
        known_students,
        threshold=MATCH_THRESHOLD,
        max_side=960,
        upsample=1,
    )
    all_ids = sorted({int(row["student_id"]) for row in (known_students or []) if row.get("student_id") is not None})
    return detected, all_ids, num_faces
