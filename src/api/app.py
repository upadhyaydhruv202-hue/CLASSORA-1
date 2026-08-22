from __future__ import annotations

import io
import importlib.util
from datetime import datetime, timezone
from typing import Optional

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
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
        from src.pipelines.face_pipeline import load_dlib_models

        load_dlib_models()
    except Exception:
        pass
    try:
        from src.pipelines.voice_pipeline import warmup_voice_encoder

        warmup_voice_encoder()
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
    face_loaded = False
    try:
        from src.pipelines.face_pipeline import dlib_ready

        face_loaded = dlib_ready()
    except Exception:
        face_loaded = False
    face_ready = all(models[key] for key in ("numpy", "dlib", "face_recognition_models"))
    voice_ready = all(models[key] for key in ("numpy", "librosa", "resemblyzer"))
    voice_loaded = False
    try:
        from src.pipelines.voice_pipeline import voice_encoder_ready

        voice_loaded = voice_encoder_ready()
    except Exception:
        voice_loaded = False
    return {
        "ok": True,
        "ui": "react",
        "streamlit": False,
        "supabase": _cloud(),
        "mode": "supabase" if _cloud() else "local-demo",
        "face_models_ready": face_ready,
        "voice_models_ready": voice_ready,
        "face_weights_loaded": face_loaded,
        "voice_weights_loaded": voice_loaded,
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
    try:
        mark_login(body.username, "teacher")
    except Exception:
        pass
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


def _attach_voice(student_id, audio_bytes, use_cloud):
    from src.pipelines.voice_pipeline import get_voice_embedding

    embedding = get_voice_embedding(audio_bytes)
    if not embedding:
        raise RuntimeError("Could not build a voice embedding from that clip.")
    if use_cloud:
        cloud.update_student_voice(student_id, embedding)
    else:
        local.update_student_voice(student_id, embedding)
    return embedding


@app.post("/api/auth/student/register")
async def student_register(
    name: str = Form(...),
    face: UploadFile | None = File(None),
    voice: UploadFile | None = File(None),
):
    face_emb = None
    voice_bytes = await voice.read() if voice else None
    if not face:
        raise HTTPException(status_code=400, detail="Capture your face to register.")
    try:
        from src.pipelines.face_pipeline import get_face_embeddings

        encodings = get_face_embeddings(_image_to_np(await face.read()))
        if not encodings:
            raise HTTPException(status_code=400, detail="No face found. Face the light, move closer, and try again.")
        if len(encodings) > 1:
            raise HTTPException(status_code=400, detail="Multiple faces found. Only one person should be in frame.")
        face_emb = encodings[0].tolist()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Face enrollment failed: {exc}") from exc
    if _cloud():
        created = cloud.create_student(name, face_embedding=face_emb, voice_embedding=None)
        student = created[0] if created else None
    else:
        student = local.create_student(name, face_embedding=face_emb, voice_embedding=None)
    if not student:
        raise HTTPException(status_code=500, detail="Could not create student profile.")
    try:
        from src.pipelines.face_pipeline import train_classifier

        train_classifier()
    except Exception:
        pass
    if voice_bytes:
        try:
            _attach_voice(student["student_id"], voice_bytes, _cloud())
        except Exception as exc:
            allowed, message = login_allowed(student["student_id"])
            if not allowed:
                raise HTTPException(status_code=403, detail=message) from exc
            mark_login(name, "student")
            payload = _token_body(session_payload(role="student", student=student))
            payload["voice_warning"] = (
                f"Account created, but voice enrollment failed: {exc}. "
                "You can still use FaceID. Record 2–4 seconds next time to enable voice attendance."
            )
            return payload
    allowed, message = login_allowed(student["student_id"])
    if not allowed:
        raise HTTPException(status_code=403, detail=message)
    mark_login(name, "student")
    return _token_body(session_payload(role="student", student=student))


@app.post("/api/auth/student/face")
async def student_face_login(face: UploadFile = File(...)):
    try:
        from src.pipelines.face_pipeline import LOGIN_THRESHOLD, predict_attendance

        img = _image_to_np(await face.read())
        if _cloud():
            roster = cloud.get_all_students("student_id, name, face_embedding") or []
        else:
            roster = local.read_db()["students"]
        detected, _all_ids, num_faces = predict_attendance(img, threshold=LOGIN_THRESHOLD)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Face scan failed: {exc}") from exc
    if num_faces == 0:
        raise HTTPException(status_code=400, detail="No face found. Move closer and try again.")
    if num_faces > 1:
        raise HTTPException(status_code=400, detail="Multiple faces found. Only one person should be in frame.")
    if not detected:
        return {"matched": False, "detail": "Face detected. You're a new student — enter your name to register."}
    student_id = int(list(detected.keys())[0])
    student = next((row for row in roster if int(row.get("student_id")) == student_id), None)
    if not student:
        raise HTTPException(status_code=404, detail="Matched student record was not found.")
    allowed, message = login_allowed(student_id)
    if not allowed:
        raise HTTPException(status_code=403, detail=message)
    mark_login(student.get("name"), "student")
    return {"matched": True, **_token_body(session_payload(role="student", student=sanitize_student(student)))}


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
    roster_ids = {int(row["student_id"]) for row in roster}
    for photo in photos:
        img = _image_to_np(await photo.read())
        detected, _all_ids, num_faces = predict_attendance(img)
        matched = {int(sid): True for sid in detected if int(sid) in roster_ids}
        unknown_faces += max(0, num_faces - len(matched))
        present.update(matched)
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
    try:
        from src.pipelines.voice_pipeline import as_voice_vector, process_bulk_audio, VoiceWarmingError
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Voice models are not available: {exc}") from exc
    candidates = {}
    for row in roster:
        emb = as_voice_vector(row.get("voice_embedding"))
        if emb is not None:
            candidates[int(row["student_id"])] = emb
    if not candidates:
        raise HTTPException(
            status_code=400,
            detail="No enrolled students in this subject have a voice profile yet. Ask them to register with a short voice clip.",
        )
    try:
        identified = process_bulk_audio(await audio.read(), candidates) or {}
    except VoiceWarmingError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
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
        return [
            row
            for row in (cloud.get_all_students("student_id, name, face_embedding, voice_embedding") or [])
            if int(row.get("student_id")) in ids
        ]
    subjects = local.teacher_subjects(teacher_id)
    if not any(int(row.get("subject_id")) == int(subject_id) for row in subjects):
        raise HTTPException(status_code=403, detail="Subject is not yours.")
    return local.students_for_subject(subject_id)
