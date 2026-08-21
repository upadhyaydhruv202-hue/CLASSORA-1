"""Face identity — original dlib 128-d + linear SVM pipeline.

Source: https://github.com/shradha-khapra/ai-attendance-project-app
  src/pipelines/face_pipeline.py

Streamlit (@st.cache_resource / st.cache_resource.clear) is replaced by a
module-level singleton so this file can run under FastAPI. Detector,
shape predictor, ResNet embeddings, SVC, and the 0.6 L2 check are unchanged.
"""
import json

import dlib
import numpy as np
import face_recognition_models
from sklearn.svm import SVC

from src.database.config import is_supabase_configured
from src.database.db import get_all_students


_dlib_models = None
_trained_model = None

FACE_SIZE = 128
MATCH_THRESHOLD = 0.6


def as_face_vector(value):
    """Parse a stored embedding (list or JSON string) for DB/API integration."""
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


def dlib_ready():
    return _dlib_models is not None


def load_dlib_models():
    global _dlib_models
    if _dlib_models is None:
        detector = dlib.get_frontal_face_detector()
        sp = dlib.shape_predictor(face_recognition_models.pose_predictor_model_location())
        facerec = dlib.face_recognition_model_v1(face_recognition_models.face_recognition_model_location())
        _dlib_models = (detector, sp, facerec)
    return _dlib_models


def get_face_embeddings(image_np):
    detector, sp, facerec = load_dlib_models()
    faces = detector(image_np, 1)

    encodings = []

    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 1)  # 128 embedding

        encodings.append(np.array(face_descriptor))
    return encodings


def _student_db():
    if is_supabase_configured():
        return get_all_students() or []
    from src.database import local_store as local

    return local.read_db().get("students") or []


def get_trained_model():
    global _trained_model
    if _trained_model is not None:
        return _trained_model

    X = []
    y = []

    student_db = _student_db()

    if not student_db:
        return None

    for student in student_db:
        embedding = student.get("face_embedding")
        vec = as_face_vector(embedding)
        if vec is None and embedding:
            vec = np.array(embedding)
        if vec is None or getattr(vec, "size", 0) != FACE_SIZE:
            continue
        X.append(np.array(vec))
        y.append(student.get("student_id"))

    if len(X) == 0:
        return 0

    clf = SVC(kernel="linear", probability=True, class_weight="balanced")

    try:
        clf.fit(X, y)
    except ValueError:
        pass

    _trained_model = {"clf": clf, "X": X, "y": y}
    return _trained_model


def invalidate_classifier():
    global _trained_model
    _trained_model = None


def train_classifier():
    invalidate_classifier()
    model_data = get_trained_model()
    return bool(model_data)


def predict_attendance(class_image_np):
    encodings = get_face_embeddings(class_image_np)

    detected_student = {}

    model_data = get_trained_model()

    if not model_data:
        return detected_student, [], len(encodings)

    clf = model_data["clf"]
    X_train = model_data["X"]
    y_train = model_data["y"]

    all_students = sorted(list(set(y_train)))

    for encoding in encodings:
        if len(all_students) >= 2:
            predicted_id = int(clf.predict([encoding])[0])
        else:
            predicted_id = int(all_students[0])

        student_embedding = X_train[y_train.index(predicted_id)]

        best_match_score = np.linalg.norm(student_embedding - encoding)

        resemblance_threshold = 0.6

        if best_match_score <= resemblance_threshold:
            detected_student[predicted_id] = True
    return detected_student, all_students, len(encodings)


def match_faces(image_np, known_rows=None, threshold=MATCH_THRESHOLD, max_side=640, upsample=1):
    """API adapter: original predict_attendance, then optional roster filter."""
    detected, _all_ids, num_faces = predict_attendance(image_np)
    if known_rows:
        allowed = set()
        for row in known_rows:
            try:
                allowed.add(int(row["student_id"]))
            except (KeyError, TypeError, ValueError):
                pass
        detected = {sid: True for sid in detected if int(sid) in allowed}
    return detected, num_faces
