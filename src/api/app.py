from __future__ import annotations

import io
import importlib.util
from datetime import datetime, timezone
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from PIL import Image

from src.api.deps import get_session, require_role, require_session
from src.auth.rbac import STAFF_ROLES
from src.auth.session import mark_login, sanitize_staff, sanitize_student, sanitize_teacher, session_payload
from src.auth.tokens import encode_token
from src.database.auth_db import password_strength
from src.database.config import get_secret, is_supabase_configured, supabase
from src.database import db as cloud
from src.database import local_store as local
from src.moderation.service import login_allowed, student_snapshot
from src.success.intelligence import load_bundle, profile_map, student_360
from src.success.risk_service import get_current_risk
from src.success.staff_auth import create_staff as cloud_create_staff
from src.success.staff_auth import staff_login as cloud_staff_login

from src.api.features import router as features_router


@asynccontextmanager
async def lifespan(_app):
    try:
        from src.pipelines.face_pipeline import get_trained_model, load_dlib_models

        load_dlib_models()
        get_trained_model()
    except Exception:
        pass
    yield


app = FastAPI(title="CLASSORA API", version="1.0.0", lifespan=lifespan)
app.include_router(features_router)

_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:4173",
]
_app_url = get_secret("APP_URL").rstrip("/")
if _app_url and _app_url not in _cors_origins:
    _cors_origins.append(_app_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_origin_regex=r"https://([a-z0-9-]+\.)*vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _cloud() -> bool:
    return is_supabase_configured()


def _token_body(session: dict) -> dict:
    return {"token": encode_token(session), "session": session}


def _image_to_np(data: bytes):
    import numpy as np

    return np.array(Image.open(io.BytesIO(data)).convert("RGB"))


class TeacherAuthIn(BaseModel):
    username: str
    password: str
    name: Optional[str] = None


class StaffAuthIn(BaseModel):
    username: str
    password: str
    name: Optional[str] = None
    role: str = "counsellor"


class SubjectIn(BaseModel):
    subject_code: str
    name: str
    section: str = "A"


class EnrollIn(BaseModel):
    subject_code: str


class AttendanceConfirmIn(BaseModel):
    subject_id: int
    present_ids: list[int] = Field(default_factory=list)
    absent_ids: list[int] = Field(default_factory=list)


def _module_ok(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


@app.get("/api/health")
def health():
    models = {
        "numpy": _module_ok("numpy"),
        "dlib": _module_ok("dlib"),
        "face_recognition_models": _module_ok("face_recognition_models"),
        "sklearn": _module_ok("sklearn"),
        "librosa": _module_ok("librosa"),
        "resemblyzer": _module_ok("resemblyzer"),
    }
    face_ready = all(models[key] for key in ("numpy", "dlib", "face_recognition_models", "sklearn"))
    voice_ready = all(models[key] for key in ("numpy", "librosa", "resemblyzer"))
    return {
        "ok": True,
        "ui": "react",
        "streamlit": False,
        "supabase": _cloud(),
        "mode": "supabase" if _cloud() else "local-demo",
        "face_models_ready": face_ready,
        "voice_models_ready": voice_ready,
        "models": models,
    }


@app.post("/api/auth/teacher/login")
def teacher_login(body: TeacherAuthIn):
    if _cloud():
        teacher = cloud.teacher_login(body.username, body.password)
    else:
        teacher = local.teacher_login(body.username, body.password)
    if not teacher:
        raise HTTPException(status_code=401, detail="Invalid teacher credentials.")
    mark_login(body.username, "teacher")
    return _token_body(session_payload(role="teacher", teacher=teacher))


@app.post("/api/auth/teacher/register")
def teacher_register(body: TeacherAuthIn):
    if not body.name:
        raise HTTPException(status_code=400, detail="Name is required.")
    ok, msg = password_strength(body.password)
    if not ok:
        raise HTTPException(status_code=400, detail=msg)
    if _cloud():
        if cloud.check_teacher_exists(body.username):
            raise HTTPException(status_code=409, detail="Username already taken.")
        created = cloud.create_teacher(body.username, body.password, body.name)
        teacher = created[0] if created else None
    else:
        if local.teacher_exists(body.username):
            raise HTTPException(status_code=409, detail="Username already taken.")
        teacher = local.create_teacher(body.username, body.password, body.name)
    if not teacher:
        raise HTTPException(status_code=500, detail="Could not create teacher.")
    return _token_body(session_payload(role="teacher", teacher=teacher))


@app.post("/api/auth/staff/login")
def staff_login(body: StaffAuthIn):
    staff = cloud_staff_login(body.username, body.password) if _cloud() else local.staff_login(body.username, body.password)
    if not staff:
        raise HTTPException(status_code=401, detail="Invalid staff credentials.")
    role = staff.get("role") or "counsellor"
    mark_login(body.username, role)
    return _token_body(session_payload(role=role, staff=staff))


@app.post("/api/auth/staff/register")
def staff_register(body: StaffAuthIn):
    if body.role not in STAFF_ROLES:
        raise HTTPException(status_code=400, detail="Invalid staff role.")
    if not body.name:
        raise HTTPException(status_code=400, detail="Name is required.")
    if _cloud():
        data, msg = cloud_create_staff(body.username, body.password, body.name, body.role)
        if not data:
            raise HTTPException(status_code=400, detail=msg)
        staff = data[0] if isinstance(data, list) else data
    else:
        ok, msg = password_strength(body.password)
        if not ok:
            raise HTTPException(status_code=400, detail=msg)
        staff = local.create_staff(body.username, body.password, body.name, body.role)
        if not staff:
            raise HTTPException(status_code=409, detail="Username already taken.")
    return _token_body(session_payload(role=body.role, staff=staff))


def _attach_voice_later(student_id, audio_bytes, use_cloud):
    try:
        from src.pipelines.voice_pipeline import get_voice_embedding

        embedding = get_voice_embedding(audio_bytes)
        if not embedding:
            return
        if use_cloud:
            cloud.update_student_voice(student_id, embedding)
        else:
            local.update_student_voice(student_id, embedding)
    except Exception:
        return


@app.post("/api/auth/student/register")
async def student_register(
    background_tasks: BackgroundTasks,
    name: str = Form(...),
    face: UploadFile | None = File(None),
    voice: UploadFile | None = File(None),
):
    face_emb = None
    voice_bytes = None
    if face:
        try:
            from src.pipelines.face_pipeline import get_face_embeddings, invalidate_classifier

            encodings = get_face_embeddings(_image_to_np(await face.read()))
            if encodings:
                face_emb = encodings[0].tolist()
            if _cloud():
                invalidate_classifier()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Face enrollment failed: {exc}") from exc
    if voice:
        voice_bytes = await voice.read()
    if _cloud():
        created = cloud.create_student(name, face_embedding=face_emb, voice_embedding=None)
        student = created[0] if created else None
    else:
        student = local.create_student(name, face_embedding=face_emb, voice_embedding=None)
    if not student:
        raise HTTPException(status_code=500, detail="Could not create student profile.")
    if voice_bytes:
        background_tasks.add_task(_attach_voice_later, student["student_id"], voice_bytes, _cloud())
    allowed, message = login_allowed(student["student_id"])
    if not allowed:
        raise HTTPException(status_code=403, detail=message)
    mark_login(name, "student")
    return _token_body(session_payload(role="student", student=student))


@app.post("/api/auth/student/face")
async def student_face_login(face: UploadFile = File(...)):
    try:
        from src.pipelines.face_pipeline import predict_attendance

        img = _image_to_np(await face.read())
        if _cloud():
            detected, _ids, num_faces = predict_attendance(img)
            roster = cloud.get_all_students("student_id, name") or []
        else:
            detected, num_faces = _match_local_faces(img)
            roster = local.read_db()["students"]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Face scan failed: {exc}") from exc
    if num_faces == 0:
        raise HTTPException(status_code=400, detail="No face found. Move closer and try again.")
    if num_faces > 1:
        raise HTTPException(status_code=400, detail="Multiple faces found. Only one person should be in frame.")
    if not detected:
        return {"matched": False, "detail": "Face detected, but no matching profile yet. Register below."}
    student_id = int(list(detected.keys())[0])
    student = next((row for row in roster if int(row.get("student_id")) == student_id), None)
    if not student:
        raise HTTPException(status_code=404, detail="Matched student record was not found.")
    allowed, message = login_allowed(student_id)
    if not allowed:
        raise HTTPException(status_code=403, detail=message)
    mark_login(student.get("name"), "student")
    return {"matched": True, **_token_body(session_payload(role="student", student=sanitize_student(student)))}


@app.post("/api/auth/student/quick")
def student_quick_login(student_id: int):
    if _cloud():
        student = cloud.get_student_public(student_id)
        if student:
            full = next((row for row in (cloud.get_all_students() or []) if int(row.get("student_id")) == int(student_id)), student)
            student = full
    else:
        student = local.public_student(local.get_student(student_id))
    if not student:
        raise HTTPException(status_code=404, detail="Student not found.")
    allowed, message = login_allowed(student["student_id"])
    if not allowed:
        raise HTTPException(status_code=403, detail=message)
    return _token_body(session_payload(role="student", student=student))


@app.get("/api/me")
def me(session: dict = Depends(require_session)):
    return session


@app.get("/api/teacher/subjects")
def teacher_subjects(session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        return cloud.get_teacher_subjects(teacher_id) or []
    return local.teacher_subjects(teacher_id)


@app.post("/api/teacher/subjects")
def teacher_create_subject(body: SubjectIn, session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        created = cloud.create_subject(body.subject_code, body.name, body.section, teacher_id)
        return created[0] if created else {"ok": True}
    created = local.create_subject(body.subject_code, body.name, body.section, teacher_id)
    if not created:
        raise HTTPException(status_code=409, detail="Subject code already exists.")
    return created


@app.get("/api/teacher/attendance")
def teacher_attendance(session: dict = Depends(require_role("teacher"))):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        return cloud.get_attendance_for_teacher(teacher_id) or []
    return local.teacher_attendance(teacher_id)


@app.get("/api/teacher/institution")
def teacher_institution(session: dict = Depends(require_role("teacher"))):
    from src.database.institution import apply_filters, build_metrics, load_teacher_institution

    teacher_id = session["teacher_data"]["teacher_id"]
    bundle = load_teacher_institution(teacher_id)
    filtered = apply_filters(bundle)
    return {"bundle": bundle, "metrics": build_metrics(filtered)}


@app.post("/api/teacher/attendance/face")
async def teacher_face_attendance(
    subject_id: int = Form(...),
    photos: list[UploadFile] = File(...),
    session: dict = Depends(require_role("teacher")),
):
    present = {}
    unknown_faces = 0
    roster = _subject_roster(session, subject_id)
    try:
        from src.pipelines.face_pipeline import predict_attendance
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Face models are not available: {exc}") from exc
    for photo in photos:
        img = _image_to_np(await photo.read())
        if _cloud():
            detected, all_ids, num_faces = predict_attendance(img)
            unknown_faces += max(0, num_faces - len(detected))
            for sid in detected:
                present[int(sid)] = True
        else:
            detected, num_faces = _match_local_faces(img, roster)
            unknown_faces += max(0, num_faces - len(detected))
            present.update({int(sid): True for sid in detected})
    present_ids = [int(sid) for sid in present]
    absent_ids = [int(row["student_id"]) for row in roster if int(row["student_id"]) not in present]
    return {
        "present_ids": present_ids,
        "absent_ids": absent_ids,
        "unknown_faces": unknown_faces,
        "roster": [sanitize_student(row) for row in roster],
    }


@app.post("/api/teacher/attendance/voice")
async def teacher_voice_attendance(
    subject_id: int = Form(...),
    audio: UploadFile = File(...),
    session: dict = Depends(require_role("teacher")),
):
    roster = _subject_roster(session, subject_id)
    candidates = {}
    try:
        import numpy as np
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"NumPy is required for voice attendance: {exc}") from exc
    for row in roster:
        emb = row.get("voice_embedding")
        if emb:
            candidates[int(row["student_id"])] = np.array(emb)
    try:
        from src.pipelines.voice_pipeline import process_bulk_audio

        identified = process_bulk_audio(await audio.read(), candidates) or {}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Voice attendance failed: {exc}") from exc
    present_ids = [int(sid) for sid in identified]
    absent_ids = [int(row["student_id"]) for row in roster if int(row["student_id"]) not in present_ids]
    return {
        "present_ids": present_ids,
        "absent_ids": absent_ids,
        "scores": {str(k): float(v) for k, v in identified.items()},
        "roster": [sanitize_student(row) for row in roster],
    }


@app.post("/api/teacher/attendance/confirm")
def teacher_confirm_attendance(body: AttendanceConfirmIn, session: dict = Depends(require_role("teacher"))):
    stamp = datetime.now(timezone.utc).isoformat()
    logs = []
    for sid in body.present_ids:
        logs.append({"student_id": int(sid), "subject_id": int(body.subject_id), "is_present": True, "timestamp": stamp})
    for sid in body.absent_ids:
        logs.append({"student_id": int(sid), "subject_id": int(body.subject_id), "is_present": False, "timestamp": stamp})
    if not logs:
        raise HTTPException(status_code=400, detail="Nothing to save.")
    if _cloud():
        saved = cloud.create_attendance(logs)
    else:
        saved = local.add_attendance(logs)
    return {"saved": len(saved or []), "timestamp": stamp}


@app.get("/api/student/directory")
def student_directory():
    if _cloud():
        rows = cloud.get_all_students("student_id, name") or []
    else:
        rows = local.list_students()
    return [sanitize_student(row) for row in rows]


@app.get("/api/student/subjects")
def student_subjects(session: dict = Depends(require_role("student"))):
    student_id = session["student_data"]["student_id"]
    if _cloud():
        subjects = cloud.get_student_subjects(student_id) or []
        logs = cloud.get_student_attendance(student_id) or []
    else:
        subjects = local.student_subjects(student_id)
        logs = local.student_attendance(student_id)
    return {"subjects": subjects, "attendance": logs}


@app.post("/api/student/enroll")
def student_enroll(body: EnrollIn, session: dict = Depends(require_role("student"))):
    student_id = session["student_data"]["student_id"]
    subject = cloud.get_subject_by_code(body.subject_code) if _cloud() else local.subject_by_code(body.subject_code)
    if not subject:
        raise HTTPException(status_code=404, detail="No subject found with that code.")
    if _cloud():
        cloud.enroll_student_to_subject(student_id, subject["subject_id"])
        return {"ok": True, "subject": subject}
    result = local.enroll(student_id, subject["subject_id"])
    if result.get("already"):
        raise HTTPException(status_code=409, detail="Already enrolled in this subject.")
    return {"ok": True, "subject": subject}


@app.delete("/api/student/subjects/{subject_id}")
def student_unenroll(subject_id: int, session: dict = Depends(require_role("student"))):
    student_id = session["student_data"]["student_id"]
    if _cloud():
        cloud.unenroll_student_to_subject(student_id, subject_id)
    else:
        local.unenroll(student_id, subject_id)
    return {"ok": True}


@app.get("/api/student/risk")
def student_risk(session: dict = Depends(require_role("student"))):
    student_id = session["student_data"]["student_id"]
    snap = student_snapshot(student_id)
    payload = get_current_risk(
        student_id,
        session_state=session,
        actor_role="student",
        actor_student_id=student_id,
    )
    return {"snapshot": snap, "risk": payload}


@app.get("/api/success/hub")
def success_hub(session: dict = Depends(require_session)):
    teacher_id = (session.get("teacher_data") or {}).get("teacher_id")
    bundle = load_bundle(session, teacher_id=teacher_id)
    ranked = profile_map(bundle)
    return {
        "demo": bool(bundle.get("demo") or session.get("demo_mode")),
        "scenario": bundle.get("scenario_label"),
        "students": ranked,
        "cases": bundle.get("cases") or [],
        "recommendations": bundle.get("recommendations") or [],
    }


@app.get("/api/success/student/{student_id}")
def success_student(student_id: int, session: dict = Depends(require_session)):
    bundle = load_bundle(session, teacher_id=(session.get("teacher_data") or {}).get("teacher_id"))
    return student_360(bundle, student_id)


def _subject_roster(session, subject_id: int):
    teacher_id = session["teacher_data"]["teacher_id"]
    if _cloud():
        subjects = cloud.get_teacher_subjects(teacher_id) or []
        if not any(int(row.get("subject_id")) == int(subject_id) for row in subjects):
            raise HTTPException(status_code=403, detail="Subject is not yours.")
        enrollments = supabase.table("subject_students").select("student_id").eq("subject_id", subject_id).execute().data or []
        ids = {int(row["student_id"]) for row in enrollments}
        return [row for row in (cloud.get_all_students("student_id, name") or []) if int(row.get("student_id")) in ids]
    subjects = local.teacher_subjects(teacher_id)
    if not any(int(row.get("subject_id")) == int(subject_id) for row in subjects):
        raise HTTPException(status_code=403, detail="Subject is not yours.")
    return local.students_for_subject(subject_id)


def _match_local_faces(img, roster=None):
    import numpy as np
    from src.pipelines.face_pipeline import get_face_embeddings

    encodings = get_face_embeddings(img)
    rows = roster if roster is not None else local.read_db()["students"]
    detected = {}
    for encoding in encodings:
        best_id = None
        best = 999
        for row in rows:
            emb = row.get("face_embedding")
            if not emb:
                continue
            score = float(np.linalg.norm(np.array(emb) - encoding))
            if score < best:
                best = score
                best_id = int(row["student_id"])
        if best_id is not None and best <= 0.6:
            detected[best_id] = True
    return detected, len(encodings)
