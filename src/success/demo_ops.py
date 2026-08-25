"""Demo accounts, outcomes, moderation, merchant, and scoped reset.

Uses existing CLASSORA auth/services. Does not write face/voice embeddings.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.database.config import is_supabase_configured, supabase
from src.database import db
from src.database import local_store as local
from src.database.db import hash_pass
from src.success import store
from src.success.demo_seed import (
    DEMO_ALERT_SOURCE,
    DEMO_ASSESSMENT_PREFIX,
    DEMO_LMS_COURSE,
    DEMO_MARK,
    DEMO_SECTION,
    _cloud,
    _enroll,
    _first,
    _insert_attendance,
    _insert_student,
    _insert_subject,
    _int,
    _iso,
    _list_students,
    _list_subjects,
    _list_teachers,
    _now,
    is_demo_student_name,
)
from src.success.staff_auth import create_staff

DEMO_PASSWORD = "DemoPass123"
DEMO_TEACHER = "DEMO_FACULTY_01"
DEMO_INSTITUTION = "CLASSORA DEMO UNIVERSITY"

STAFF_ACCOUNTS = (
    ("DEMO_ADMIN", "administrator", "Demo Administrator"),
    ("DEMO_FACULTY_STAFF", "faculty", "Demo Faculty Staff"),
    ("DEMO_COUNSELLOR_01", "counsellor", "Demo Counsellor 01"),
    ("DEMO_COUNSELLOR_02", "counsellor", "Demo Counsellor 02"),
    ("DEMO_MENTOR_01", "mentor", "Demo Mentor 01"),
    ("DEMO_MENTOR_02", "mentor", "Demo Mentor 02"),
)

FACULTY_SUBJECTS = (
    {"code": "DEMO-CS201", "name": "Applied Algorithms"},
    {"code": "DEMO-LAB201", "name": "Programming Lab"},
)


def _admin_session():
    return {"user_role": "administrator", "staff_data": {"username": "DEMO_ADMIN", "name": "Demo Administrator"}}


def ensure_staff_accounts(counts: dict) -> dict[str, int]:
    ids = {}
    existing = {str(row.get("username")): row for row in (store.select("staff_users") or [])}
    for username, role, name in STAFF_ACCOUNTS:
        row = existing.get(username)
        if not row:
            data, msg = create_staff(username, DEMO_PASSWORD, name, role)
            if not data:
                counts.setdefault("staff_errors", []).append(f"{username}: {msg}")
                continue
            row = data[0] if isinstance(data, list) else data
            counts["staff_created"] = counts.get("staff_created", 0) + 1
        else:
            counts["staff_reused"] = counts.get("staff_reused", 0) + 1
        sid = _int((row or {}).get("staff_id"))
        if sid is not None:
            ids[username] = sid
    counts["staff"] = len(ids)
    return ids


def ensure_demo_teacher(counts: dict) -> dict | None:
    teachers = _list_teachers()
    found = next((row for row in teachers if str(row.get("username")) == DEMO_TEACHER), None)
    if found:
        counts["teacher_reused"] = 1
        return found
    try:
        if _cloud():
            data = db.create_teacher(DEMO_TEACHER, DEMO_PASSWORD, "Demo Faculty 01")
        else:
            data = local.create_teacher(DEMO_TEACHER, DEMO_PASSWORD, "Demo Faculty 01")
        row = _first(data)
        counts["teacher_created"] = 1
        return row
    except Exception as exc:
        counts.setdefault("teacher_errors", []).append(str(exc))
        return None


def ensure_faculty_subjects(teacher: dict | None, profiles: dict, counts: dict) -> None:
    if not teacher:
        counts["faculty_subjects_skipped"] = "no_demo_teacher"
        return
    teacher_id = _int(teacher.get("teacher_id"))
    existing = {str(row.get("subject_code")): row for row in _list_subjects()}
    subject_ids = []
    for spec in FACULTY_SUBJECTS:
        row = existing.get(spec["code"])
        if not row:
            row = _insert_subject(spec["code"], spec["name"], teacher_id)
            counts["faculty_subjects_created"] = counts.get("faculty_subjects_created", 0) + 1
        if row:
            subject_ids.append(_int(row.get("subject_id")))
    from src.success.demo_seed import _existing_demo_attendance, build_attendance_logs
    for profile in profiles.values():
        sid = profile["student_id"]
        for subject_id in subject_ids:
            if subject_id is None:
                continue
            _enroll(sid, subject_id)
        if _existing_demo_attendance(sid, [i for i in subject_ids if i is not None]):
            continue
        if len(subject_ids) < 2:
            continue
        # Reuse the 4-subject generator against the two faculty subjects by cycling ids.
        padded = list(subject_ids) + list(subject_ids)
        logs = build_attendance_logs(profile, padded[:4])
        logs = [row for row in logs if row.get("subject_id") in set(subject_ids)]
        counts["faculty_attendance"] = counts.get("faculty_attendance", 0) + _insert_attendance(logs)


def ensure_institution(counts: dict) -> None:
    from src.success.ops import settings_payload

    rows = store.select("institution_settings") or []
    current = settings_payload((rows[0] or {}).get("settings") if rows else {})
    name = current.get("institution_name") or ""
    if name and "DEMO" not in name.upper() and name.strip():
        counts["institution_skipped"] = "existing_name_preserved"
        if not current.get("support_note"):
            merged = dict(current)
            merged["support_note"] = "Roster may include prototype demo records labeled (Demo)."
            if rows:
                store.update("institution_settings", {"id": rows[0].get("id", 1)}, {"settings": merged})
        return
    payload = {
        "institution_name": DEMO_INSTITUTION,
        "support_note": "DEMO DATA — NOT REAL STUDENT DATA. Prototype records for feature demonstration.",
    }
    if rows:
        store.update("institution_settings", {"id": rows[0].get("id", 1)}, {"settings": payload})
        counts["institution_updated"] = 1
    else:
        store.insert("institution_settings", {"id": 1, "settings": payload})
        counts["institution_created"] = 1


def seed_outcomes(profiles: dict, counts: dict) -> None:
    existing = store.select("student_academic_outcomes") or []
    by_student = {}
    for row in existing:
        if str(row.get("recorded_by") or "") != "demo_seed":
            continue
        by_student[_int(row.get("student_id"))] = row
    created = 0
    for profile in profiles.values():
        sid = profile["student_id"]
        if sid in by_student:
            continue
        status = str(profile.get("outcome") or "ACTIVE").upper()
        saved = store.insert("student_academic_outcomes", {
            "student_id": sid,
            "status": status,
            "period": "Demo 2025-26",
            "notes": "Prototype academic outcome for dropout RCA. Not an institutional filing.",
            "recorded_by": "demo_seed",
            "recorded_at": _iso(_now() - timedelta(days=20)),
        })
        created += len(saved or [])
    counts["outcomes"] = created
    counts["outcomes_existing"] = len(by_student)


def seed_closed_support(profiles: dict, counts: dict) -> None:
    aarav = profiles.get("AARAV")
    if aarav:
        code = "CASE-DEMO-AARAV-CLOSED"
        existing = [row for row in (store.select("intervention_cases") or []) if row.get("case_code") == code]
        if not existing:
            saved = store.insert("intervention_cases", {
                "case_code": code,
                "student_id": aarav["student_id"],
                "owner": "DEMO_COUNSELLOR_01",
                "priority": "low",
                "status": "closed",
                "intervention_name": "Mentor weekly meeting",
                "deadline": _iso(_now() - timedelta(days=3)),
                "notes": "Prototype closed case.",
                "closed_at": _iso(_now() - timedelta(days=1)),
                "closure_reason": "Demo recovered",
            })
            case = _first(saved)
            if case:
                store.insert("intervention_outcomes", {
                    "case_id": case.get("id"),
                    "classification": "improved",
                    "notes": "Prototype positive outcome.",
                    "recorded_by": "demo_seed",
                })
                counts["closed_cases"] = 1
                counts["outcomes_cases"] = 1
        tara = profiles.get("TARA")
        if tara:
            alerts = store.select("alerts", student_id=tara["student_id"]) or []
            if not any(row.get("source") == DEMO_ALERT_SOURCE and row.get("status") == "resolved" for row in alerts):
                store.insert("alerts", {
                    "student_id": tara["student_id"],
                    "source": DEMO_ALERT_SOURCE,
                    "severity": "low",
                    "title": "Demo · Resolved attendance watch",
                    "status": "resolved",
                    "owner": "DEMO_COUNSELLOR_01",
                    "resolved_at": _iso(),
                })
                counts["resolved_alerts"] = 1
        jobs = [row for row in (store.select("import_jobs") or []) if str(row.get("filename") or "").startswith("demo-")]
        if not jobs:
            store.insert("import_jobs", {
                "kind": "academic",
                "filename": "demo-academic-valid.csv",
                "status": "completed",
                "summary": "Prototype import job. Fixture only.",
            })
            store.insert("import_jobs", {
                "kind": "lms",
                "filename": "demo-lms-invalid.csv",
                "status": "failed",
                "summary": "Prototype failed import. Invalid student_id.",
            })
            counts["import_jobs"] = 2


def seed_moderation(profiles: dict, staff_ids: dict, counts: dict) -> None:
    from src.moderation import service as moderation
    from src.success.notify import notify

    if not moderation.installed():
        counts["moderation_skipped"] = "schema_unavailable"
        return
    tara = profiles.get("TARA")
    counsellor_id = staff_ids.get("DEMO_COUNSELLOR_01")
    admin_id = staff_ids.get("DEMO_ADMIN")
    if not tara or not counsellor_id:
        counts["moderation_skipped"] = "missing_actor"
        return
    sid = tara["student_id"]
    existing = [
        row for row in (store.select("complaints") or [])
        if _int(row.get("student_id")) == sid and "[Demo]" in str(row.get("description") or "")
    ]
    if not existing:
        row, msg = moderation.create_complaint(
            reporter_role="counsellor",
            reporter_staff_id=counsellor_id,
            student_reference=str(sid),
            category="Misuse of platform",
            severity="medium",
            description="[Demo] Prototype complaint for workflow demonstration. Not a real incident report.",
            requested_action="temporary_restriction",
        )
        if not row:
            counts["complaint_error"] = msg
        else:
            counts["complaints"] = 1
            store.update("complaints", {"complaint_id": row.get("complaintId") or row.get("complaint_id")}, {
                "status": "UNDER_REVIEW",
            })
            notify(
                role="administrator",
                recipient_id="ops",
                title="[Demo] Complaint under review",
                body="Prototype complaint is on the admin caseload.",
            )
            counts["moderation_notifications"] = 1
    else:
        counts["complaints_existing"] = 1
    status_rows = store.select("student_moderation_status", student_id=sid) or []
    if not status_rows:
        store.insert("student_moderation_status", {
            "student_id": sid,
            "status": "RESTRICTED",
            "until_at": _iso(_now() + timedelta(days=7)),
            "reason": "Demo restriction so an appeal can be demonstrated.",
            "updated_by_staff_id": admin_id,
            "updated_at": _iso(),
        })
        counts["moderation_status"] = 1
    appeals = [
        row for row in (store.select("student_appeals") or [])
        if _int(row.get("student_id")) == sid and "[Demo]" in str(row.get("reason") or "")
    ]
    if not appeals:
        saved, msg = moderation.submit_appeal(
            student_id=sid,
            reason="[Demo] Please restore access for the prototype demonstration.",
            explanation="This is a prototype appeal, not a real student filing.",
        )
        if saved:
            counts["appeals"] = 1
            if admin_id:
                moderation.review_appeal(
                    appeal_id=saved.get("id"),
                    admin_staff_id=admin_id,
                    admin_role="administrator",
                    decision="reject",
                    admin_note="[Demo] Rejected to show the reviewed state. Not a real disciplinary decision.",
                )
                counts["appeals_reviewed"] = 1
        else:
            counts["appeal_error"] = msg


def seed_merchant(profiles: dict, counts: dict) -> None:
    from src.rewards import service as rewards

    rewards.ensure_seed()
    session = _admin_session()
    existing = [row for row in (store.select("campus_merchants") or []) if "Demo Campus Canteen" in str(row.get("name") or "")]
    if existing:
        merchant = existing[0]
        counts["merchant_reused"] = 1
    else:
        merchant, msg = rewards.upsert_merchant(session, {
            "name": "Demo Campus Canteen (Demo)",
            "category": "FOOD",
            "location": "Demo campus food court",
            "contact": "demo-merchant@classora.example",
            "description": "Prototype merchant for voucher demonstration.",
            "access_code": DEMO_PASSWORD,
        })
        if not merchant:
            counts["merchant_error"] = msg
            return
        counts["merchant_created"] = 1
        merchant = {"id": merchant.get("id"), **merchant}
    mid = merchant.get("id")
    counts["merchant_id"] = mid
    offers = [row for row in (store.select("reward_offers") or []) if str(row.get("title") or "").startswith("Demo ·")]
    if not offers:
        offer, msg = rewards.upsert_offer(session, {
            "merchantId": mid,
            "title": "Demo · Tea 10% off",
            "description": "Prototype voucher. Not a real canteen offer.",
            "discountType": "PERCENTAGE",
            "discountValue": 10,
            "pointsCost": 50,
            "terms": "Demo dataset only.",
        })
        if offer:
            counts["reward_offers"] = 1
        else:
            counts["offer_error"] = msg
    aarav = profiles.get("AARAV")
    if aarav and offers or counts.get("reward_offers"):
        live_offers = [row for row in (store.select("reward_offers") or []) if str(row.get("title") or "").startswith("Demo ·")]
        if live_offers and aarav:
            student_session = {"user_role": "student", "student_data": {"student_id": aarav["student_id"], "name": aarav["name"]}}
            vouchers = [row for row in (store.select("reward_vouchers") or []) if _int(row.get("student_id")) == aarav["student_id"]]
            if not vouchers:
                claimed, msg = rewards.claim_offer(student_session, live_offers[0].get("id"), idempotency_key="demo-seed:AARAV:tea")
                if claimed:
                    counts["vouchers"] = 1
                else:
                    counts["voucher_error"] = msg


def integrity_report() -> dict:
    students = [row for row in _list_students() if is_demo_student_name(row.get("name"))]
    ids = {_int(row.get("student_id")) for row in students if _int(row.get("student_id")) is not None}
    orphans = []
    for table, field in (
        ("academic_records", "student_id"),
        ("lms_events", "student_id"),
        ("intervention_cases", "student_id"),
        ("alerts", "student_id"),
    ):
        for row in store.select(table) or []:
            if "Demo" not in str(row.get("assessment") or row.get("course_code") or row.get("case_code") or row.get("source") or row.get("title") or ""):
                continue
            sid = _int(row.get(field))
            if sid is not None and sid not in ids:
                orphans.append(f"{table}:{sid}")
    kinds = {}
    try:
        rows = store.select("mentorships") or []
        for row in rows:
            if _int(row.get("student_id")) in ids:
                kinds.setdefault(_int(row.get("student_id")), set()).add(str(row.get("kind") or "unknown"))
    except Exception:
        rows = []
    both = sum(1 for kinds_set in kinds.values() if "mentor" in kinds_set and "counsellor" in kinds_set)
    complaints = [
        row for row in (store.select("complaints") or [])
        if _int(row.get("student_id")) in ids and "[Demo]" in str(row.get("description") or "")
    ]
    return {
        "demo_students": len(students),
        "orphan_demo_rows": orphans[:20],
        "students_with_both_mentoring_and_counselling": both,
        "demo_complaints": len(complaints),
        "staff_demo": [row.get("username") for row in (store.select("staff_users") or []) if str(row.get("username") or "").startswith("DEMO_")],
    }


def reset_demo_data() -> dict:
    """Delete only records labeled as CLASSORA demo. Never drops unnamed production rows."""
    removed = {}
    students = [row for row in _list_students() if is_demo_student_name(row.get("name"))]
    sids = [_int(row.get("student_id")) for row in students if _int(row.get("student_id")) is not None]
    subjects = [row for row in _list_subjects() if str(row.get("subject_code") or "").startswith("DEMO-")]
    sub_ids = [_int(row.get("subject_id")) for row in subjects if _int(row.get("subject_id")) is not None]
    demo_slugs = (
        "demo-coding-club",
        "demo-sports-circle",
        "demo-cultural-circle",
        "demo-academic-study",
        "demo-campus-activities",
        "demo-festive-committee",
    )

    def _del(table, **eq):
        try:
            data = store.delete(table, **eq)
            return len(data or [])
        except Exception:
            return 0

    def _sb_del(table, **eq):
        try:
            q = supabase.table(table).delete()
            for key, value in eq.items():
                q = q.eq(key, value)
            q.execute()
            return True
        except Exception as exc:
            _del(table, **eq)
            removed.setdefault("delete_notes", []).append(f"{table}:{exc}")
            return False

    if _cloud():
        # Complaints/appeals restrict student and staff deletes.
        for sid in sids:
            _sb_del("complaints", student_id=sid)
            _sb_del("student_appeals", student_id=sid)
            _sb_del("moderation_actions", student_id=sid)
            _sb_del("mentorships", student_id=sid)
            _sb_del("reward_vouchers", student_id=sid)
        for row in store.select("notifications") or []:
            if str(row.get("title") or "").startswith("[Demo]") and row.get("id") is not None:
                _sb_del("notifications", id=row.get("id"))
        for row in store.select("import_jobs") or []:
            if str(row.get("filename") or "").startswith("demo-") and row.get("id") is not None:
                _sb_del("import_jobs", id=row.get("id"))
        try:
            for sid in sids:
                supabase.table("attendance_logs").delete().eq("student_id", sid).execute()
            for sub in sub_ids:
                supabase.table("attendance_logs").delete().eq("subject_id", sub).execute()
            removed["attendance"] = "cleared_demo_students"
        except Exception as exc:
            removed["attendance_error"] = str(exc)
        for sid in sids:
            for table in (
                "academic_records", "lms_events", "alerts", "intervention_cases",
                "intervention_recommendations", "recovery_plans", "recovery_tasks",
                "appointments", "student_context", "student_academic_outcomes",
                "reward_achievements", "reward_transactions", "reward_badges", "reward_milestones",
                "community_members",
            ):
                _sb_del(table, student_id=sid)
            _sb_del("students", student_id=sid)
        for sub in sub_ids:
            _sb_del("subject_students", subject_id=sub)
            _sb_del("subjects", subject_id=sub)
        for slug in demo_slugs:
            community = next((row for row in (store.select("communities") or []) if str(row.get("slug")) == slug), None)
            cid = (community or {}).get("id")
            if cid is not None:
                for table in ("community_comments", "community_reactions", "community_posts", "community_events", "community_members"):
                    _sb_del(table, community_id=cid)
            _sb_del("communities", slug=slug)
        for row in store.select("campus_merchants") or []:
            if "Demo Campus Canteen" not in str(row.get("name") or ""):
                continue
            mid = row.get("id")
            for offer in store.select("reward_offers") or []:
                title = str(offer.get("title") or "")
                if _int(offer.get("merchant_id")) != _int(mid) and not title.startswith("Demo ·"):
                    continue
                oid = offer.get("id")
                for voucher in store.select("reward_vouchers") or []:
                    if voucher.get("offer_id") != oid:
                        continue
                    _sb_del("voucher_redemptions", voucher_id=voucher.get("id"))
                    _sb_del("reward_vouchers", id=voucher.get("id"))
                _sb_del("reward_offers", id=oid)
            _sb_del("campus_merchants", id=mid)
            removed["merchant"] = mid
        for username, _role, _name in STAFF_ACCOUNTS:
            _sb_del("staff_users", username=username)
        _sb_del("teachers", username=DEMO_TEACHER)
        removed["students"] = len(sids)
    else:
        data = local.read_db()
        data["students"] = [row for row in data.get("students") or [] if not is_demo_student_name(row.get("name"))]
        data["subjects"] = [row for row in data.get("subjects") or [] if not str(row.get("subject_code") or "").startswith("DEMO-")]
        data["subject_students"] = [
            row for row in data.get("subject_students") or []
            if _int(row.get("student_id")) not in sids and _int(row.get("subject_id")) not in sub_ids
        ]
        data["attendance_logs"] = [
            row for row in data.get("attendance_logs") or []
            if _int(row.get("student_id")) not in sids
        ]
        data["staff_users"] = [
            row for row in data.get("staff_users") or []
            if not str(row.get("username") or "").startswith("DEMO_")
        ]
        data["teachers"] = [row for row in data.get("teachers") or [] if str(row.get("username")) != DEMO_TEACHER]
        local._dump(data)
        removed["local"] = True
        removed["students"] = len(sids)
    return removed


def seed_extras(profiles: dict, counts: dict, staff_ids: dict | None = None, teacher: dict | None = None) -> None:
    staff_ids = staff_ids or ensure_staff_accounts(counts)
    if teacher is None:
        teacher = ensure_demo_teacher(counts)
    ensure_faculty_subjects(teacher, profiles, counts)
    ensure_institution(counts)
    seed_outcomes(profiles, counts)
    seed_closed_support(profiles, counts)
    seed_moderation(profiles, staff_ids, counts)
    seed_merchant(profiles, counts)
    try:
        from src.dropout import service as dropout

        result = dropout.run_analysis(None, actor="demo_seed")
        overview = result.get("overview") or {}
        counts["dropout_insufficient"] = bool(result.get("insufficient"))
        counts["dropout_enrolled"] = overview.get("enrolled")
        counts["dropout_dropouts"] = overview.get("dropouts")
        counts["dropout_factors"] = len(result.get("factors") or [])
    except Exception as exc:
        counts["dropout_error"] = str(exc)
    try:
        from src.cohort import service as cohort

        result = cohort.run_analysis(None, actor="demo_seed")
        counts["anomalies"] = len(result.get("anomalies") or result.get("events") or [])
        counts["anomaly_insufficient"] = bool(result.get("insufficient"))
    except Exception as exc:
        counts["anomaly_error"] = str(exc)
    counts["integrity"] = integrity_report()
