"""Prediction orchestration: ingest, classify, analyze, query, history, RBAC."""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from src.predictions import classify as C
from src.predictions import engine as E
from src.predictions import extract as X
from src.predictions import policy as P
from src.success import store

logger = logging.getLogger("classora.predictions")

_RATES = defaultdict(deque)
_RATE_WINDOW = 3600
_RATE_LIMITS = {
    "upload": 30,
    "query": 60,
    "analyze": 20,
}

VIEW_ROLES = ("student", "teacher", "faculty", "mentor", "counsellor", "administrator")
UPLOAD_ROLES = VIEW_ROLES
STAFF_ROLES = ("teacher", "faculty", "mentor", "counsellor", "administrator")
SETTINGS_ROLES = ("administrator",)
INSTITUTION_UPLOAD_ROLES = STAFF_ROLES


def _now():
    return datetime.now(timezone.utc)


def _iso(value=None):
    if value is None:
        return _now().isoformat()
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _jsonish(value, default=None):
    if isinstance(value, (dict, list)):
        return value
    return default if default is not None else {}


def institution_id():
    return P.INSTITUTION_ID


def actor_name(session):
    if not session:
        return ""
    if session.get("staff_data"):
        return session["staff_data"].get("username") or session["staff_data"].get("name") or ""
    if session.get("teacher_data"):
        return session["teacher_data"].get("username") or ""
    if session.get("student_data"):
        return session["student_data"].get("name") or ""
    return session.get("user_role") or ""


def actor_id(session):
    if not session:
        return ""
    role = session.get("user_role")
    if role == "student":
        return str((session.get("student_data") or {}).get("student_id") or "")
    if role == "teacher":
        return str((session.get("teacher_data") or {}).get("teacher_id") or "")
    return str((session.get("staff_data") or {}).get("staff_id") or actor_name(session))


def student_id(session):
    return _int((session.get("student_data") or {}).get("student_id"))


def audit(session, action, entity="", entity_id="", reason=""):
    store.insert("audit_events", {
        "actor": actor_name(session),
        "action": action,
        "entity": f"{entity}:{entity_id}" if entity_id else entity,
        "detail": (reason or "")[:400],
    })


def _rate(session, action):
    key = f"{session.get('user_role')}:{actor_id(session)}:{action}"
    now = time.time()
    bucket = _RATES[key]
    while bucket and now - bucket[0] > _RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= _RATE_LIMITS.get(action, 30):
        return False
    bucket.append(now)
    return True


def get_settings():
    rows = store.select("prediction_settings") or []
    raw = _jsonish(rows[0].get("settings"), {}) if rows else {}
    return P.normalize_settings(raw)


def save_settings(raw, session):
    if session.get("user_role") not in SETTINGS_ROLES:
        return None, "FORBIDDEN"
    cfg = P.normalize_settings(raw)
    existing = store.select("prediction_settings") or []
    payload = {"settings": cfg, "updated_at": _iso()}
    if existing:
        store.update("prediction_settings", {"id": existing[0].get("id", 1)}, payload)
    else:
        store.insert("prediction_settings", {"id": 1, **payload})
    audit(session, "prediction_settings_updated", "prediction_settings")
    return cfg, ""


def ensure_seed():
    if not (store.select("prediction_settings") or []):
        store.insert("prediction_settings", {"id": 1, "settings": P.normalize_settings(), "updated_at": _iso()})


def _can_view(session):
    return session.get("user_role") in VIEW_ROLES


def public_document(row, session, include_text=False):
    if not row:
        return None
    role = session.get("user_role")
    sid = student_id(session)
    owner = _int(row.get("owner_student_id"))
    visibility = str(row.get("visibility") or "PRIVATE")
    is_owner = role == "student" and owner is not None and owner == sid
    is_staff = role in STAFF_ROLES
    institution_ok = visibility == "INSTITUTION"
    if role == "student" and not is_owner and not institution_ok:
        return None
    if is_staff and visibility == "PRIVATE" and not institution_ok:
        return None
    out = {
        "id": row.get("id"),
        "title": row.get("title") or row.get("filename") or "Untitled",
        "filename": row.get("filename") or "",
        "documentType": row.get("document_type") or "UNKNOWN",
        "typeOverride": row.get("type_override") or "",
        "subject": row.get("subject") or "UNKNOWN",
        "year": row.get("year"),
        "semester": row.get("semester") or "UNKNOWN",
        "academicYear": row.get("academic_year") or "UNKNOWN",
        "domain": row.get("domain") or "ACADEMIC",
        "visibility": visibility,
        "official": bool(row.get("official")),
        "sourceReliability": row.get("source_reliability") or "LOWER",
        "status": row.get("status"),
        "error": row.get("error_message") or "",
        "contentHash": row.get("content_hash") or "",
        "sourceUrl": row.get("source_url") or "",
        "uploadedAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
        "analyzedAt": row.get("analyzed_at"),
        "ownerStudentId": owner if is_staff and visibility == "INSTITUTION" else (owner if is_owner else None),
        "injectionFlag": bool(row.get("injection_flag")),
        "charCount": len(str(row.get("extracted_text") or "")),
    }
    if include_text:
        if is_owner or (is_staff and institution_ok) or (role == "student" and institution_ok):
            out["extractedText"] = row.get("extracted_text") or ""
        else:
            return None
    return out


def _all_docs():
    return [row for row in (store.select("prediction_documents") or []) if str(row.get("status")) != "DELETED"]


def visible_documents(session, include_text=False):
    role = session.get("user_role")
    sid = student_id(session)
    out = []
    for row in _all_docs():
        visibility = str(row.get("visibility") or "PRIVATE")
        owner = _int(row.get("owner_student_id"))
        if role == "student":
            if owner == sid or visibility == "INSTITUTION":
                pub = public_document(row, session, include_text=include_text)
                if pub:
                    out.append(row if include_text else {**row, **{}})
                    if not include_text:
                        out[-1] = row
        elif role in STAFF_ROLES:
            if visibility == "INSTITUTION":
                out.append(row)
    if include_text:
        return out
    return [public_document(row, session) for row in out if public_document(row, session)]


def _raw_visible(session):
    role = session.get("user_role")
    sid = student_id(session)
    rows = []
    for row in _all_docs():
        visibility = str(row.get("visibility") or "PRIVATE")
        owner = _int(row.get("owner_student_id"))
        if role == "student" and (owner == sid or visibility == "INSTITUTION"):
            rows.append(row)
        elif role in STAFF_ROLES and visibility == "INSTITUTION":
            rows.append(row)
    return rows


def get_document(session, doc_id, include_text=False):
    if not _can_view(session):
        return None, "FORBIDDEN"
    row = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), None)
    if not row:
        return None, "NOT_FOUND"
    pub = public_document(row, session, include_text=include_text)
    if not pub:
        return None, "FORBIDDEN"
    return pub, ""


def _process_document(row):
    doc_id = row.get("id")
    store.update("prediction_documents", {"id": doc_id}, {"status": "PROCESSING", "updated_at": _iso()})
    try:
        store.update("prediction_documents", {"id": doc_id}, {"status": "EXTRACTING", "updated_at": _iso()})
        text = row.get("extracted_text") or ""
        if not str(text).strip():
            store.update("prediction_documents", {"id": doc_id}, {
                "status": P.FAILED_STATUS,
                "error_message": "Empty document.",
                "updated_at": _iso(),
            })
            return None, "EMPTY_DOCUMENT"
        store.update("prediction_documents", {"id": doc_id}, {"status": "ANALYZING", "updated_at": _iso()})
        classified = C.classify_document(
            text,
            filename=row.get("filename") or "",
            user_type=row.get("type_override") or "",
            user_subject=row.get("subject_override") or "",
        )
        store.update("prediction_documents", {"id": doc_id}, {"status": "INDEXING", "updated_at": _iso()})
        store.delete("prediction_items", document_id=doc_id)
        items = []
        dtype = classified["documentType"]
        if dtype in {"PYQ", "QUESTION_BANK"}:
            for q in X.extract_questions(text):
                items.append({
                    "document_id": doc_id,
                    "item_type": "QUESTION",
                    "raw_text": q["raw"],
                    "normalized_text": q["raw"].lower(),
                    "topic_key": C.topic_key_for_question(q["raw"]),
                    "year": classified.get("year") or row.get("year"),
                    "marks": q.get("marks"),
                    "extra": {"questionType": q.get("questionType")},
                })
        if dtype in {"EXAM_SCHEDULE", "ACADEMIC_CALENDAR"} or row.get("official"):
            for parsed in X.parse_dates(text):
                items.append({
                    "document_id": doc_id,
                    "item_type": "DATE",
                    "raw_text": parsed["raw"],
                    "normalized_text": parsed["date"],
                    "topic_key": C.nearby_subject(text, parsed["span"]),
                    "year": parsed["year"],
                    "marks": None,
                    "extra": parsed,
                })
        for topic in classified.get("topics") or []:
            items.append({
                "document_id": doc_id,
                "item_type": "TOPIC",
                "raw_text": topic["label"],
                "normalized_text": topic["topic"],
                "topic_key": topic["topic"],
                "year": classified.get("year") or row.get("year"),
                "marks": None,
                "extra": {"aliases": topic.get("aliases") or []},
            })
        if P.domain_for_type(dtype) == "CAREER" or dtype in P.CAREER_TYPES:
            for skill in X.extract_skills(text):
                items.append({
                    "document_id": doc_id,
                    "item_type": "SKILL",
                    "raw_text": skill,
                    "normalized_text": skill.lower(),
                    "topic_key": skill,
                    "year": classified.get("year"),
                    "marks": None,
                    "extra": {},
                })
            for amount in X.parse_stipends(text):
                items.append({
                    "document_id": doc_id,
                    "item_type": "STIPEND",
                    "raw_text": str(amount),
                    "normalized_text": str(amount),
                    "topic_key": "STIPEND",
                    "year": classified.get("year"),
                    "marks": amount,
                    "extra": {},
                })
        for item in items:
            store.insert("prediction_items", item)
        values = {
            "document_type": dtype,
            "subject": classified["subject"] if not row.get("subject_override") else row.get("subject_override"),
            "year": classified.get("year") or row.get("year"),
            "semester": classified.get("semester") or "UNKNOWN",
            "academic_year": classified.get("academicYear") or "UNKNOWN",
            "department": "UNKNOWN",
            "course": "UNKNOWN",
            "domain": classified.get("domain") or P.domain_for_type(dtype),
            "source_reliability": P.reliability_for(dtype, official=bool(row.get("official")), user_rank=row.get("source_reliability")),
            "status": P.READY_STATUS,
            "error_message": "",
            "analyzed_at": _iso(),
            "updated_at": _iso(),
            "classification": classified,
        }
        store.update("prediction_documents", {"id": doc_id}, values)
        fresh = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), None)
        return fresh, ""
    except Exception:
        logger.exception("prediction document failed")
        store.update("prediction_documents", {"id": doc_id}, {
            "status": P.FAILED_STATUS,
            "error_message": "Processing failed. You can retry.",
            "updated_at": _iso(),
        })
        return None, "PROCESSING_FAILED"


def ingest_text(session, payload):
    if session.get("user_role") not in UPLOAD_ROLES:
        return None, "FORBIDDEN"
    if not _rate(session, "upload"):
        return None, "RATE_LIMITED"
    ensure_seed()
    cfg = get_settings()
    if not cfg.get("enabled"):
        return None, "FEATURE_DISABLED"
    text = X.clean_text(payload.get("content") or payload.get("text") or "", cfg["max_text_chars"])
    source_url = str(payload.get("sourceUrl") or payload.get("source_url") or "").strip()
    if source_url and not text:
        return None, "URL_FETCH_DISABLED"
    if not text:
        return None, "EMPTY_DOCUMENT"
    filename = str(payload.get("filename") or payload.get("title") or "pasted.txt")
    title = str(payload.get("title") or filename or "Untitled").strip()[:200]
    digest = X.sha256_text(text)
    role = session.get("user_role")
    sid = student_id(session)
    visibility = "INSTITUTION" if role in INSTITUTION_UPLOAD_ROLES else "PRIVATE"
    if role == "student":
        visibility = "PRIVATE"
    existing = [
        row for row in _all_docs()
        if row.get("content_hash") == digest
        and str(row.get("institution_id") or institution_id()) == institution_id()
        and str(row.get("owner_student_id") or "") == str(sid or "")
        and str(row.get("visibility") or "") == visibility
    ]
    if existing:
        pub = public_document(existing[0], session)
        if pub:
            pub["duplicate"] = True
            return pub, "DUPLICATE"
    official = bool(payload.get("official")) if role in STAFF_ROLES else False
    user_type = P.normalize_type(payload.get("documentType") or payload.get("document_type") or "")
    if user_type in {"UNKNOWN", "OTHER"}:
        user_type = ""
    subject_override = str(payload.get("subject") or "").strip().upper()
    row = {
        "institution_id": institution_id(),
        "owner_student_id": sid if role == "student" else None,
        "uploaded_by": actor_name(session),
        "uploaded_role": role,
        "visibility": visibility,
        "title": title,
        "filename": filename,
        "content_hash": digest,
        "document_type": "UNKNOWN",
        "type_override": user_type,
        "subject": subject_override or "UNKNOWN",
        "subject_override": subject_override if subject_override and subject_override != "UNKNOWN" else "",
        "year": _int(payload.get("year")),
        "semester": "UNKNOWN",
        "academic_year": "UNKNOWN",
        "department": "UNKNOWN",
        "course": "UNKNOWN",
        "domain": "ACADEMIC",
        "source_reliability": "MEDIUM",
        "official": official,
        "source_url": source_url,
        "extracted_text": text,
        "status": "UPLOADED",
        "error_message": "",
        "injection_flag": P.looks_like_injection(text),
        "created_at": _iso(),
        "updated_at": _iso(),
    }
    saved = store.insert("prediction_documents", row)
    if not saved:
        return None, "SAVE_FAILED"
    created = saved[0]
    processed, err = _process_document(created)
    if not processed:
        failed = next((item for item in (store.select("prediction_documents") or []) if str(item.get("id")) == str(created.get("id"))), created)
        pub = public_document(failed, session) or {"id": created.get("id"), "status": P.FAILED_STATUS, "error": err}
        return pub, err or "PROCESSING_FAILED"
    audit(session, "prediction_document_ingested", "prediction_documents", processed.get("id"))
    pub = public_document(processed, session)
    pub["duplicate"] = False
    return pub, ""


def ingest_file(session, filename, data, extra=None):
    extra = extra or {}
    cfg = get_settings()
    problem = X.validate_upload(filename, len(data or b""), max_bytes=cfg["max_upload_bytes"])
    if problem:
        return None, problem
    text, err = X.extract_file(filename, data or b"")
    if err:
        return None, err
    payload = {
        **extra,
        "content": text,
        "filename": filename,
        "title": extra.get("title") or filename,
    }
    return ingest_text(session, payload)


def reprocess(session, doc_id):
    if not _can_view(session):
        return None, "FORBIDDEN"
    row = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), None)
    if not row:
        return None, "NOT_FOUND"
    if not public_document(row, session):
        return None, "FORBIDDEN"
    role = session.get("user_role")
    owner = _int(row.get("owner_student_id"))
    if role == "student" and owner != student_id(session):
        return None, "FORBIDDEN"
    processed, err = _process_document(row)
    if not processed:
        return public_document(row, session), err or "PROCESSING_FAILED"
    return public_document(processed, session), ""


def update_document(session, doc_id, payload):
    row = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), None)
    if not row:
        return None, "NOT_FOUND"
    if not public_document(row, session):
        return None, "FORBIDDEN"
    role = session.get("user_role")
    owner = _int(row.get("owner_student_id"))
    if role == "student" and owner != student_id(session):
        return None, "FORBIDDEN"
    values = {"updated_at": _iso()}
    if payload.get("title"):
        values["title"] = str(payload["title"])[:200]
    if payload.get("documentType") or payload.get("document_type"):
        values["type_override"] = P.normalize_type(payload.get("documentType") or payload.get("document_type"))
        values["document_type"] = values["type_override"]
    if payload.get("subject"):
        values["subject_override"] = str(payload["subject"]).strip().upper()
        values["subject"] = values["subject_override"]
    if role in STAFF_ROLES and "official" in payload:
        values["official"] = bool(payload.get("official"))
        values["source_reliability"] = P.reliability_for(values.get("document_type") or row.get("document_type"), official=values["official"])
    store.update("prediction_documents", {"id": row.get("id")}, values)
    if any(k in values for k in ("type_override", "subject_override", "official")):
        return reprocess(session, row.get("id"))
    fresh = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), row)
    return public_document(fresh, session), ""


def delete_document(session, doc_id):
    row = next((item for item in _all_docs() if str(item.get("id")) == str(doc_id)), None)
    if not row:
        return None, "NOT_FOUND"
    if not public_document(row, session):
        return None, "FORBIDDEN"
    role = session.get("user_role")
    owner = _int(row.get("owner_student_id"))
    if role == "student" and owner != student_id(session):
        return None, "FORBIDDEN"
    if role in STAFF_ROLES and str(row.get("visibility")) != "INSTITUTION" and role != "administrator":
        return None, "FORBIDDEN"
    store.delete("prediction_items", document_id=row.get("id"))
    store.delete("prediction_documents", id=row.get("id"))
    audit(session, "prediction_document_deleted", "prediction_documents", row.get("id"))
    return {"ok": True, "id": row.get("id")}, ""


def _profile(session, extra=None):
    extra = extra or {}
    sid = student_id(session)
    profile = {
        "studentId": sid,
        "weakAreas": extra.get("weakAreas") or extra.get("weak_areas") or [],
        "strongAreas": extra.get("strongAreas") or extra.get("strong_areas") or [],
        "hours": extra.get("hours") or extra.get("hoursPerDay"),
        "attendanceRate": None,
        "records": [],
    }
    if sid is None:
        return profile
    try:
        logs = store.select("attendance_logs", student_id=sid) or []
        if logs:
            present = sum(1 for row in logs if row.get("is_present") in (True, 1, "1", "true"))
            profile["attendanceRate"] = round(100.0 * present / len(logs), 1)
    except Exception:
        pass
    try:
        records = store.select("academic_records", student_id=sid) or []
        profile["records"] = [
            {"subject": row.get("subject") or row.get("course"), "score": row.get("score") or row.get("marks")}
            for row in records[:20]
        ]
    except Exception:
        pass
    return profile


def _persist_result(session, kind, payload, subject="", mode="GENERAL"):
    sid = student_id(session)
    row = {
        "institution_id": institution_id(),
        "student_id": sid,
        "prediction_type": kind,
        "subject": subject or "",
        "mode": mode,
        "prediction": payload,
        "confidence": payload.get("confidence") or (payload.get("questions") or [{}])[0].get("confidence") if payload.get("questions") else payload.get("status"),
        "data_period": payload.get("dataPeriod") or payload.get("analyzedUntil") or "",
        "status": payload.get("status") or "READY",
        "generated_at": _iso(),
        "analysis_version": P.ANALYSIS_VERSION,
    }
    saved = store.insert("prediction_results", row)
    result = saved[0] if saved else row
    result_id = result.get("id")
    evidence_rows = []
    for item in payload.get("evidence") or []:
        evidence_rows.append(item)
    for topic in (payload.get("questions") or payload.get("studyPriorities") or [])[:8]:
        evidence_rows.extend(topic.get("evidence") or [])
    for item in evidence_rows[:40]:
        store.insert("prediction_evidence", {
            "prediction_id": result_id,
            "source_document_id": item.get("documentId"),
            "source_reference": item.get("title") or "",
            "evidence_text": item.get("snippet") or "",
            "relevance_score": 1.0,
            "kind": item.get("kind") or "OBSERVED",
        })
    return result


def _history(session, question, payload, kind, subject="", mode="GENERAL"):
    sid = student_id(session)
    store.insert("prediction_history", {
        "institution_id": institution_id(),
        "student_id": sid,
        "question": question,
        "prediction_type": kind,
        "subject": subject or "",
        "mode": mode,
        "payload": payload,
        "confidence": payload.get("confidence") or "",
        "status": payload.get("status") or "READY",
        "generated_at": _iso(),
        "data_period": payload.get("dataPeriod") or "",
        "analysis_version": P.ANALYSIS_VERSION,
    })


def analyze(session, payload=None):
    if not _can_view(session):
        return None, "FORBIDDEN"
    if not _rate(session, "analyze"):
        return None, "RATE_LIMITED"
    ensure_seed()
    cfg = get_settings()
    if not cfg.get("enabled"):
        return None, "FEATURE_DISABLED"
    payload = payload or {}
    subject = str(payload.get("subject") or "").strip().upper()
    if subject == "UNKNOWN":
        subject = ""
    mode = P.normalize_mode(payload.get("mode"))
    domain = P.normalize_domain(payload.get("domain")) or "ALL"
    docs = _raw_visible(session)
    out = {
        "disclaimer": P.DISCLAIMER,
        "decisionNote": P.DECISION_DISCLAIMER,
        "analyzedUntil": _iso(),
        "capabilities": X.capabilities(),
        "mode": mode,
        "subject": subject or "UNKNOWN",
        "weights": cfg["weights"],
    }
    if domain in {"", "ALL", "ACADEMIC", "INSTITUTIONAL"}:
        out["academic"] = E.academic_analysis(docs, cfg, subject=subject, mode=mode)
        out["examDate"] = E.exam_date_prediction(docs, cfg, subject=subject, target_year=payload.get("targetYear") or payload.get("target_year"))
        profile = _profile(session, payload)
        out["plan"] = E.study_plan(
            out["academic"].get("studyPriorities") or [],
            days=payload.get("days") or 7,
            hours=payload.get("hours") or payload.get("hoursPerDay") or 3,
            subjects=[subject] if subject else None,
            mode=mode,
            profile=profile,
        )
        out["readiness"] = E.readiness(out["academic"].get("topics") or [], profile)
        out["today"] = E.today_focus(out["academic"].get("studyPriorities") or [], out.get("examDate"))
    if domain in {"", "ALL", "CAREER"}:
        out["career"] = E.career_analysis(docs, cfg, mode=mode)
        resume_docs = [d for d in docs if P.normalize_type(d.get("document_type")) == "RESUME"]
        job_docs = [d for d in docs if P.normalize_type(d.get("document_type")) == "JOB"]
        resume_text = payload.get("resumeText") or payload.get("resume_text") or (resume_docs[-1].get("extracted_text") if resume_docs else "")
        job_text = payload.get("jobText") or payload.get("job_text") or (job_docs[-1].get("extracted_text") if job_docs else "")
        out["jobMatch"] = E.job_match(resume_text, job_text)
        skill_labels = [row["label"] for row in (out["career"].get("skills") or [])]
        if resume_text:
            skill_labels = list({*skill_labels, *X.extract_skills(resume_text)})
        out["careerPaths"] = E.career_paths(skill_labels)
        out["hackathonPrep"] = E.hackathon_prep(out["career"])
    result = _persist_result(session, "ANALYZE", out, subject=subject, mode=mode)
    out["resultId"] = result.get("id")
    return out, ""


def query(session, payload):
    if not _can_view(session):
        return None, "FORBIDDEN"
    if not _rate(session, "query"):
        return None, "RATE_LIMITED"
    ensure_seed()
    cfg = get_settings()
    if not cfg.get("enabled"):
        return None, "FEATURE_DISABLED"
    question = str(payload.get("question") or payload.get("q") or "").strip()
    if not question:
        return None, "EMPTY_QUERY"
    routed = E.route_query(question)
    subject = str(payload.get("subject") or routed.get("subject") or "").strip().upper()
    if subject == "UNKNOWN":
        subject = ""
    mode = P.normalize_mode(payload.get("mode") or routed.get("mode"))
    docs = _raw_visible(session)
    academic = E.academic_analysis(docs, cfg, subject=subject, mode=mode)
    exam_date = E.exam_date_prediction(docs, cfg, subject=subject, target_year=payload.get("targetYear"))
    career = E.career_analysis(docs, cfg, mode=mode)
    profile = _profile(session, payload)
    days = payload.get("days") or routed.get("days") or 7
    hours = payload.get("hours") or payload.get("hoursPerDay") or routed.get("hours") or 3
    intent = routed["intent"]
    card = None
    kind = intent
    if intent in {"IMPORTANT_QUESTIONS", "ACADEMIC_PRIORITY", "STUDY_FIRST"}:
        card = {
            "title": f"{subject or 'Academic'} predictive study priority",
            "kind": "PREDICTED",
            "items": academic.get("studyPriorities") or [],
            "status": academic.get("status"),
            "insufficientReason": academic.get("insufficientReason"),
            "confidence": (academic.get("studyPriorities") or [{}])[0].get("confidence") if academic.get("studyPriorities") else "VERY_LOW",
            "disclaimer": academic.get("disclaimer") or P.DISCLAIMER,
        }
    elif intent == "EXAM_DATE":
        card = exam_date
    elif intent == "PASS_FOCUSED":
        focused = E.academic_analysis(docs, cfg, subject=subject, mode="PASS_FOCUSED")
        card = {
            "title": "Minimum-viable preparation",
            "kind": "RECOMMENDED",
            "items": focused.get("studyPriorities") or [],
            "status": focused.get("status"),
            "insufficientReason": focused.get("insufficientReason"),
            "disclaimer": f"{P.DISCLAIMER} {P.PASS_DISCLAIMER}",
        }
        academic = focused
    elif intent == "HIGH_SCORE":
        high = E.academic_analysis(docs, cfg, subject=subject, mode="HIGH_SCORE")
        card = {
            "title": "High-score preparation",
            "kind": "RECOMMENDED",
            "items": high.get("studyPriorities") or [],
            "status": high.get("status"),
            "disclaimer": high.get("disclaimer") or P.DISCLAIMER,
        }
        academic = high
    elif intent == "STUDY_PLAN":
        card = E.study_plan(academic.get("studyPriorities") or [], days=days, hours=hours, subjects=[subject] if subject else None, mode=mode, profile=profile)
    elif intent == "STIPEND":
        card = career.get("stipend")
    elif intent == "JOB_MATCH":
        resume_docs = [d for d in docs if P.normalize_type(d.get("document_type")) == "RESUME"]
        job_docs = [d for d in docs if P.normalize_type(d.get("document_type")) == "JOB"]
        card = E.job_match(
            payload.get("resumeText") or (resume_docs[-1].get("extracted_text") if resume_docs else ""),
            payload.get("jobText") or (job_docs[-1].get("extracted_text") if job_docs else ""),
        )
    elif intent == "INTERVIEW_ROUNDS":
        card = {
            "title": "Interview rounds observed in uploaded records",
            "kind": "OBSERVED",
            "pattern": "GENERAL_INDUSTRY",
            "items": career.get("rounds") or [],
            "status": career.get("status"),
            "disclaimer": P.CAREER_DISCLAIMER,
            "note": "These rounds appear in the uploaded experiences. They are not a guarantee for any company.",
        }
    elif intent == "HACKATHON":
        card = E.hackathon_prep(career)
    elif intent in {"INTERNSHIP", "SKILL_DEMAND"}:
        card = {
            "title": "Skills observed in uploaded internship/job records",
            "kind": "OBSERVED",
            "items": career.get("skills") or [],
            "status": career.get("status"),
            "insufficientReason": career.get("insufficientReason"),
            "disclaimer": P.CAREER_DISCLAIMER,
        }
    elif intent == "CAREER_PATH":
        resume_docs = [d for d in docs if P.normalize_type(d.get("document_type")) == "RESUME"]
        skills = X.extract_skills(resume_docs[-1].get("extracted_text") if resume_docs else "")
        if not skills:
            skills = [row["label"] for row in (career.get("skills") or [])]
        card = {
            "title": "Possible pathways from current uploaded skills",
            "kind": "RECOMMENDED",
            "items": E.career_paths(skills),
            "status": "READY" if skills else "INSUFFICIENT",
            "disclaimer": P.DECISION_DISCLAIMER,
        }
    else:
        card = {
            "title": "Predictive study priority",
            "items": academic.get("studyPriorities") or [],
            "status": academic.get("status"),
            "disclaimer": P.DISCLAIMER,
        }
    answer = {
        "question": question,
        "intent": intent,
        "subject": subject or "UNKNOWN",
        "mode": mode,
        "card": card,
        "academic": academic,
        "examDate": exam_date,
        "career": career,
        "today": E.today_focus(academic.get("studyPriorities") or [], exam_date),
        "disclaimer": P.DISCLAIMER,
        "decisionNote": P.DECISION_DISCLAIMER,
        "analyzedUntil": _iso(),
        "format": "PREDICTION",
    }
    result = _persist_result(session, kind, answer, subject=subject, mode=mode)
    _history(session, question, answer, kind, subject=subject, mode=mode)
    answer["resultId"] = result.get("id")
    return answer, ""


def list_history(session, limit=30):
    if not _can_view(session):
        return None, "FORBIDDEN"
    rows = store.select("prediction_history") or []
    role = session.get("user_role")
    sid = student_id(session)
    out = []
    for row in rows:
        owner = _int(row.get("student_id"))
        if role == "student" and owner != sid:
            continue
        if role in STAFF_ROLES and owner:
            continue
        out.append({
            "id": row.get("id"),
            "question": row.get("question"),
            "predictionType": row.get("prediction_type"),
            "subject": row.get("subject"),
            "mode": row.get("mode"),
            "confidence": row.get("confidence"),
            "status": row.get("status"),
            "generatedAt": row.get("generated_at"),
            "dataPeriod": row.get("data_period"),
            "payload": _jsonish(row.get("payload"), {}),
        })
    out.sort(key=lambda row: str(row.get("generatedAt") or ""), reverse=True)
    return out[: max(1, min(100, int(limit or 30)))], ""


def record_outcome(session, history_id, payload):
    if session.get("user_role") not in STAFF_ROLES and session.get("user_role") != "student":
        return None, "FORBIDDEN"
    rows = store.select("prediction_history") or []
    row = next((item for item in rows if str(item.get("id")) == str(history_id)), None)
    if not row:
        return None, "NOT_FOUND"
    if session.get("user_role") == "student" and _int(row.get("student_id")) != student_id(session):
        return None, "FORBIDDEN"
    saved = store.insert("prediction_outcomes", {
        "prediction_id": row.get("id"),
        "student_id": row.get("student_id"),
        "actual_outcome": str(payload.get("actualOutcome") or payload.get("actual_outcome") or "")[:400],
        "observed_at": payload.get("observedAt") or _iso(),
        "notes": str(payload.get("notes") or "")[:400],
        "created_by": actor_name(session),
    })
    if not saved:
        return None, "SAVE_FAILED"
    return saved[0], ""


def list_plans(session):
    if not _can_view(session):
        return None, "FORBIDDEN"
    rows = store.select("prediction_plans") or []
    sid = student_id(session)
    role = session.get("user_role")
    out = []
    for row in rows:
        owner = _int(row.get("student_id"))
        if role == "student" and owner != sid:
            continue
        if role in STAFF_ROLES:
            continue
        out.append({
            "id": row.get("id"),
            "subject": row.get("subject"),
            "mode": row.get("mode"),
            "days": _jsonish(row.get("items"), []),
            "updatedAt": row.get("updated_at"),
            "userModified": bool(row.get("user_modified")),
        })
    return out, ""


def save_plan(session, payload):
    if session.get("user_role") != "student":
        return None, "FORBIDDEN"
    sid = student_id(session)
    if sid is None:
        return None, "FORBIDDEN"
    items = payload.get("days") or payload.get("items") or []
    row = {
        "institution_id": institution_id(),
        "student_id": sid,
        "subject": str(payload.get("subject") or ""),
        "mode": P.normalize_mode(payload.get("mode")),
        "items": items,
        "user_modified": bool(payload.get("userModified") or payload.get("user_modified")),
        "updated_at": _iso(),
        "created_at": _iso(),
    }
    plan_id = payload.get("id")
    if plan_id:
        existing = next((item for item in (store.select("prediction_plans") or []) if str(item.get("id")) == str(plan_id)), None)
        if not existing or _int(existing.get("student_id")) != sid:
            return None, "FORBIDDEN"
        store.update("prediction_plans", {"id": existing.get("id")}, {
            "items": items,
            "user_modified": True,
            "updated_at": _iso(),
            "subject": row["subject"] or existing.get("subject"),
            "mode": row["mode"],
        })
        return {"id": existing.get("id"), "ok": True}, ""
    saved = store.insert("prediction_plans", row)
    if not saved:
        return None, "SAVE_FAILED"
    return {"id": saved[0].get("id"), "ok": True}, ""


def overview(session):
    if not _can_view(session):
        return None, "FORBIDDEN"
    docs = visible_documents(session)
    ready = [d for d in docs if d and d.get("status") == P.READY_STATUS]
    failed = [d for d in docs if d and d.get("status") == P.FAILED_STATUS]
    history, _ = list_history(session, limit=5)
    return {
        "documentCount": len(docs),
        "readyCount": len(ready),
        "failedCount": len(failed),
        "recentHistory": history or [],
        "capabilities": X.capabilities(),
        "disclaimer": P.DISCLAIMER,
        "decisionNote": P.DECISION_DISCLAIMER,
        "modes": list(P.MODES),
        "types": list(P.DOCUMENT_TYPES),
        "weights": get_settings().get("weights"),
        "settings": get_settings() if session.get("user_role") in SETTINGS_ROLES else None,
    }, ""


def student_summary(session):
    sid = student_id(session)
    if sid is None:
        return {"available": False}
    ensure_seed()
    docs = [d for d in visible_documents(session) if d]
    history, _ = list_history(session, limit=1)
    return {
        "available": True,
        "documentCount": len(docs),
        "readyCount": sum(1 for d in docs if d.get("status") == P.READY_STATUS),
        "lastQuery": (history or [{}])[0].get("question") if history else "",
    }


def evidence_for(session, result_id):
    if not _can_view(session):
        return None, "FORBIDDEN"
    rows = store.select("prediction_evidence", prediction_id=_int(result_id, result_id)) or []
    if not rows:
        rows = [row for row in (store.select("prediction_evidence") or []) if str(row.get("prediction_id")) == str(result_id)]
    allowed_ids = {str(d.get("id")) for d in _raw_visible(session)}
    out = []
    for row in rows:
        doc_id = str(row.get("source_document_id") or "")
        if doc_id and doc_id not in allowed_ids:
            continue
        out.append({
            "documentId": row.get("source_document_id"),
            "title": row.get("source_reference"),
            "snippet": row.get("evidence_text"),
            "kind": row.get("kind") or "OBSERVED",
        })
    return out, ""
