import dlib
import numpy as np
import face_recognition_models
from PIL import Image
from sklearn.svm import SVC

from src.database.db import get_all_students

_dlib_models = None
_trained_model = None


def _shrink(image_np, max_side=640):
    image = Image.fromarray(image_np)
    image.thumbnail((max_side, max_side))
    return np.array(image)


def load_dlib_models():
    global _dlib_models
    if _dlib_models is None:
        detector = dlib.get_frontal_face_detector()

        sp = dlib.shape_predictor(
            face_recognition_models.pose_predictor_model_location()
        )

        facerec = dlib.face_recognition_model_v1(
            face_recognition_models.face_recognition_model_location()
        )

        _dlib_models = (detector, sp, facerec)

    return _dlib_models

def get_face_embeddings(image_np, max_side=640):
    detector, sp, facerec = load_dlib_models()
    image_np = _shrink(image_np, max_side=max_side)
    faces = detector(image_np, 0)

    encodings = []

    for face in faces:
        shape = sp(image_np, face)
        face_descriptor = facerec.compute_face_descriptor(image_np, shape, 0)
        encodings.append(np.array(face_descriptor))
    return encodings

def get_trained_model():
    global _trained_model
    if _trained_model is not None:
        return _trained_model

    X = []
    y = []


    student_db = get_all_students("student_id, face_embedding")

    if not student_db:
        return None
    
    for student in student_db:
        embedding = student.get('face_embedding')
        if embedding:
            X.append(np.array(embedding))
            y.append(student.get('student_id'))

    if len(X) ==0:
        return 0
    
    clf = SVC(kernel="linear", class_weight="balanced")

    try:
        clf.fit(X, y)
    except ValueError:
        pass

    _trained_model = {'clf': clf, 'X':X, "y":y}
    return _trained_model


def invalidate_classifier():
    global _trained_model
    _trained_model = None


def train_classifier():
    invalidate_classifier()
    model_data = get_trained_model()
    return bool(model_data)

def predict_attendance(class_image_np):
    encodings = get_face_embeddings(class_image_np, max_side=960)

    detected_student = {}


    model_data = get_trained_model()

    if not model_data:
        return detected_student, [], len(encodings)
    
    clf = model_data['clf']
    X_train = model_data['X']
    y_train = model_data['y']

    all_students = sorted(list(set(y_train)))

    for encoding in encodings:
        if len(all_students)>= 2:
            predicted_id= int(clf.predict([encoding])[0])
        else:
            predicted_id = int(all_students[0])

        student_embedding = X_train[y_train.index(predicted_id)]

        best_match_score = np.linalg.norm(student_embedding - encoding)

        resemblance_threshold = 0.6

        if best_match_score <= resemblance_threshold:
            detected_student[predicted_id] = True
    return detected_student, all_students, len(encodings)
