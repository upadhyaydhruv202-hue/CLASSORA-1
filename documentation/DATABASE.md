# CLASSORA database

CLASSORA uses **PostgreSQL on Supabase** when `SUPABASE_URL` and `SUPABASE_KEY` are set. Otherwise the API uses a **file-backed JSON store**.

There is no Alembic/Prisma migrator. Apply SQL by pasting files into the Supabase SQL Editor.

Run order:

1. `supabase/schema.sql`
2. `supabase/schema_auth.sql` (no-op if those tables already exist)
3. `supabase/schema_success.sql`
4. `supabase/schema_mentorship.sql`
5. `supabase/schema_moderation.sql`
6. `supabase/schema_academic_resources.sql`

---

## Local fallback

| File | When |
| --- | --- |
| `data/local_db.json` | No Supabase: teachers, students, subjects, enrollment, attendance, staff, invites, auth events |
| `data/success_store.json` | Success-layer rows that are allowed offline |

`data/` is gitignored. Mentorship and complaint tables are **cloud-only** (`src/success/store.py` `_CLOUD_ONLY`). Assigning mentorship or filing complaints without Supabase will not persist those records.

---

## Core classroom (`schema.sql`)

| Table | Purpose |
| --- | --- |
| `teachers` | Username, bcrypt `password`, display name |
| `students` | Name; `face_embedding` and `voice_embedding` as JSON arrays |
| `subjects` | Code, name, section, `teacher_id` |
| `subject_students` | Enrollment (unique student+subject) |
| `attendance_logs` | `student_id`, `subject_id`, `timestamp`, `is_present` |
| `auth_events` | Login/invite audit rows |
| `teacher_invites` | Hashed invite token, expiry, used_at |

Embeddings are never sent back through `sanitize_student` / session payloads.

---

## Student Success (`schema_success.sql`)

Additive. Does not alter face/voice columns.

| Table | Purpose in code |
| --- | --- |
| `staff_users` | Staff login (`administrator`, `counsellor`, `faculty`, `mentor`) |
| `staff_invites` | Admin-created staff invites |
| `academic_records` | Optional scores/GPA/backlogs used by the risk model **if rows exist** |
| `lms_events` | Optional engagement events; no LMS connector writes these automatically |
| `student_context` | Optional workload/self-report notes |
| `risk_predictions` | Persisted scores when the risk service writes them |
| `alerts` | Early-warning rows (workspace also derives alerts in memory) |
| `intervention_library` | Catalogue; UI also ships a Python `DEFAULT_LIBRARY` |
| `intervention_cases` / `_recommendations` / `_outcomes` | Human-review loop via `store.insert` |
| `recovery_plans` / `recovery_tasks` | Recovery tasks shown in the hub |
| `notifications` / `messages` | In-app notices and help queue |
| `appointments` | Student-requested meetings |
| `audit_events` | Success-layer audit |

The Python insert payloads do not always include every `NOT NULL` column declared in SQL (for example `intervention_cases.case_code`). If a cloud insert fails, `store.insert` returns `None` and does not raise. Attendance **reads** used by risk scoring come from `attendance_logs`, which are written by the confirm-attendance path.

---

## Mentorship (`schema_mentorship.sql`)

| Table | Purpose |
| --- | --- |
| `mentor_profiles` | Caseload cap / availability |
| `mentorships` | Lifecycle statuses (`ASSIGNED` → anonymous → feedback → reveal / reject / suspend) |
| `anonymous_profiles` | Alias per party |
| `mentor_assignments` | Assignment history |
| `mentorship_sessions` | Logged meetings |
| `mentorship_messages` | Alias-scoped chat |
| related feedback / notification tables in the same file | Feedback due dates and in-app notices |

Identity stripping for faculty vs student views is done in `src/mentorship/service.py`, not in SQL views.

---

## Moderation (`schema_moderation.sql`)

| Table | Purpose |
| --- | --- |
| `student_moderation_status` | `ACTIVE` / `RESTRICTED` / `SUSPENDED` / `BANNED` — gates login |
| `complaints` | Faculty/teacher reports; requested action ≠ executed action |
| `complaint_evidence` / `complaint_reviews` / `complaint_messages` | Review trail |
| `moderation_actions` | Admin execute: warning, restrict, suspend, ban, restore |
| `student_appeals` | Student appeals |
| `moderation_audit_logs` | Audit |

SQL comments state authorization is enforced in Python. RLS is on, with `anon`/`authenticated` policies `using (true)` for this project style.

---

## Academic resources (`schema_academic_resources.sql`)

Additive directory of **metadata + original URLs**. Does not scrape or re-host PDFs.

| Table | Purpose |
| --- | --- |
| `academic_resource_sources` | Senior websites (Brain Spot, LDRP, ColleGPT, later sources) |
| `academic_resource_types` | Catalog-driven types (`NOTES`, `PYQ`, …). New types do not require frontend changes |
| `academic_resource_subjects` | Hub subjects (`year_id` `YEAR_1`–`YEAR_4`, `semester_id` `SEM_1`–`SEM_8`) |
| `academic_resources` | Title, original URL, format, source, type, subject. Unique `(subject_id, resource_type_id, original_url)` |
| `academic_resource_reports` | Student broken-link reports (`PENDING` / `REVIEWED` / `RESOLVED` / `DISMISSED`) |

Indexes cover year, semester, subject, type, source, and `is_active`. Inactive resources and inactive sources are hidden from students. Without this SQL on Supabase, the hub APIs return an install message; the local JSON store can still persist rows when Supabase is not configured.

---

## How the app reads students for ML

Face SVM training selects `student_id, face_embedding` only (`get_all_students("student_id, face_embedding")`).  
Directory and FaceID roster select `student_id, name` so embeddings are not pulled into those JSON responses.
