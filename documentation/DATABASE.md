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
7. `supabase/schema_cohort_anomalies.sql`
8. `supabase/schema_dropout_root_cause.sql`
9. `supabase/schema_rewards.sql`
10. `supabase/schema_secure_attendance.sql`
11. `supabase/schema_predictions.sql`
12. `supabase/schema_communities.sql`

---

## Local fallback

| File | When |
| --- | --- |
| `data/local_db.json` | No Supabase: teachers, students, subjects, enrollment, attendance, staff, invites, auth events |
| `data/success_store.json` | Success-layer rows that are allowed offline, including academic-resource, institutional-anomaly, dropout-analysis, rewards, secure-attendance, prediction, and community tables when those Supabase tables are missing |

`data/` is gitignored. Mentorship and complaint/appeal tables are **cloud-only** (`src/success/store.py` `_CLOUD_ONLY`: `mentorships`, `mentorship_messages`, `complaints`, `student_moderation_status`, `student_appeals`). Assigning mentorship or filing complaints/appeals without those Supabase tables will not persist those records.

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

## Institutional cohort anomalies (`schema_cohort_anomalies.sql`)

Additive institutional intelligence. Does not alter attendance, risk predictions, or individual student scores.

| Table | Purpose |
| --- | --- |
| `institutional_anomalies` | Cohort-level events with score, severity, lifecycle status, hypotheses |
| `institutional_anomaly_metrics` | Per-metric baseline/current/z-score rows for one event |
| `institutional_anomaly_snapshots` | Weekly (and current-window) aggregate observations |
| `institutional_anomaly_notes` | Admin/faculty investigation notes |
| `institutional_anomaly_settings` | Configurable thresholds and last analysis metadata |

Cohorts are derived from existing `subjects.section`, `subjects` (course), optional `academic_records.semester`, and `subjects.teacher_id`. There is no department, year, or academic-calendar table in CLASSORA, so those dimensions are not invented. If the SQL has not been applied, `store.py` can keep these tables in `data/success_store.json` the same way academic-resource tables fall back locally.

---

## Institutional dropout root-cause (`schema_dropout_root_cause.sql`)

Additive institutional intelligence. Does not alter attendance, risk predictions, or individual student scores.

| Table | Purpose |
| --- | --- |
| `student_academic_outcomes` | Explicit enrollment outcomes (`ACTIVE`, `DROPPED_OUT`, `WITHDRAWN`, `GRADUATED`, `TRANSFERRED`, `DISCONTINUED`). `DROPPED_OUT`, `WITHDRAWN`, and `DISCONTINUED` count as observed dropout. Risk scores are never treated as dropouts. |
| `institutional_dropout_analyses` | Cached analysis payload, keyed by institution + version + period |
| `institutional_dropout_factors` | Ranked associated factors for one analysis |
| `institutional_dropout_slices` | Section / semester / course aggregates |
| `institutional_dropout_intersections` | Factor-combination rows |
| `institutional_dropout_settings` | Configurable sample-size and threshold settings |

CLASSORA has no department, student-year, fee, or scholarship tables. Organizational drill-down uses `subjects.section`. Financial instability is marked `NOT_AVAILABLE` rather than invented.

---

## CLASSORA Rewards (`schema_rewards.sql`)

Additive. Does not alter students, attendance, risk, mentorship, or dropout tables. There is no `students.reward_points` column.

| Table | Purpose |
| --- | --- |
| `reward_settings` | Institution program flags (enable/disable, expiry days, caps, education level). Current deploy default is `UNDERGRADUATE`. |
| `reward_categories` | Configurable achievement categories |
| `reward_policies` | Versioned point rules. Changing a policy increments `version`; historical ledger rows keep the points they were issued with. |
| `reward_achievements` | Submissions and staff awards, with evidence metadata and idempotency keys |
| `reward_transactions` | Immutable-style ledger (`EARN`, `REDEEM`, `EXPIRE`, `ADJUSTMENT`, `REVERSAL`, `REFUND`, `BONUS`, `PENALTY`). Corrections are new rows. |
| `reward_milestones` / `reward_badges` | Lifetime point badges; separate from the ledger |
| `reward_notice_log` | Dedupes expiry reminders |
| `campus_merchants` | On-campus outlets; access codes are stored as bcrypt hashes |
| `reward_offers` | Marketplace inventory and per-student limits |
| `reward_vouchers` | Claimed instances. The redemption secret is stored as SHA-256 (`token_hash`); the plaintext token is returned once at claim. |
| `voucher_redemptions` | Merchant confirmations |

Reward Points are a closed-loop institutional currency. The schema does not support cash-out or bank transfer. If the SQL has not been applied, `store.py` can keep these tables in `data/success_store.json`.

---

## Secure multi-layer attendance (`schema_secure_attendance.sql`)

Additive. Does **not** change `attendance_logs`, embeddings, or the existing faculty confirm API.

| Table | Purpose |
| --- | --- |
| `secure_attendance_settings` | Verification mode, QR/code expiry, device binding, feature flags |
| `attendance_sessions` | Cryptographic `public_id`, subject, faculty, expiry, status |
| `attendance_face_results` | Per-face status (`FACE_MATCHED` / `UNCERTAIN` / `UNKNOWN`) and L2-derived confidence. Uncertain faces are not assigned to a student. |
| `attendance_marks` | One row per student per session. Unique `(session_id, student_id)`. `PRESENT` is the only final present state. |
| `attendance_tokens` | SHA-256 of QR tokens and secret codes. Single-use, short-lived. |
| `attendance_devices` | Hashed device secrets. Raw secrets are shown once. |
| `attendance_audit` | Session, verification, and manual-correction history |
| `attendance_disputes` | Student-raised attendance disputes |

When a mark becomes `PRESENT`, the service also writes a normal `attendance_logs` row so existing risk/analytics keep working. Pending, rejected, and expired marks are never counted as present. There is no outbound email transport in CLASSORA; email verification stays off unless a mailer is added later.

---

## Predictive Intelligence (`schema_predictions.sql`)

Additive. Does not alter academic resource URLs, face/voice embeddings, rewards, or attendance.

There is no vector database and no LLM in this engine. Extracted text is stored so frequency, recency, syllabus overlap, and date-window statistics can be recomputed. Binaries are not kept.

| Table | Purpose |
| --- | --- |
| `prediction_settings` | Configurable scoring weights, current academic year, minimum sample sizes |
| `prediction_documents` | Ingested text, content hash, classification, official flag, visibility, status |
| `prediction_items` | Extracted questions, topics, dates, skills, stipend figures |
| `prediction_results` | Latest analysis payloads with confidence and data period |
| `prediction_evidence` | Source document + snippet citations |
| `prediction_history` | Student/staff questions and answers for later review |
| `prediction_outcomes` | Optional actual-vs-predicted notes. Not used to auto-retrain. |
| `prediction_plans` | Student-editable study plans |

Student uploads are `PRIVATE`. Staff uploads are `INSTITUTION` and may be marked official. Private student text is not returned to other students or to staff. If the SQL has not been applied, `store.py` can keep these tables in `data/success_store.json`.

---

## Communities (`schema_communities.sql`)

Additive interest communities. Does not alter `students.name` visibility elsewhere. Community APIs resolve display identity from `community_privacy` and omit hidden fields.

| Table | Purpose |
| --- | --- |
| `community_settings` / `community_categories` | Feature flags and admin-managed categories |
| `communities` | Approved communities (`ACTIVE` / `SUSPENDED` / `ARCHIVED`) |
| `community_requests` | Student creation requests with duplicate flags |
| `community_members` | Unique `(community_id, student_id)` membership + role |
| `community_privacy` | Optional identity sharing; all flags default false |
| `community_posts` / `_comments` / `_reactions` | Feed. Author is `student_id` only |
| `community_events` / `_event_regs` | Practice/workshop events |
| `community_resources` | Title + safe http(s) URL or note |
| `community_reports` / `_moderation` | Reports and audit actions |
| `community_blocks` | Student-to-student hide |

There is no enrollment-number column in CLASSORA. The default public identifier is numeric `student_id`.

---

## Demo dataset

Purpose: prototype demonstration and feature validation so existing screens have coherent rows to aggregate.

Type: synthetic / seed data. **Not** institutional student records and **not** empirical college statistics.

Command: `py -3.11 scripts/seed_demo_data.py` (`src/success/demo_seed.py`). Safe to re-run. Uses positive `students.student_id` values created by the existing students table (negative IDs from `src/success/demo_data.py` are never written to production).

Coverage (existing tables only):

- `students` — display names labeled `(Demo)`, no face/voice embeddings
- `subjects` / `subject_students` / `attendance_logs` — `DEMO-*` subject codes
- `academic_records` — assessments prefixed `Demo ·`
- `lms_events` — `course_code = DEMO-HUB`
- `alerts`, `intervention_cases`, `intervention_recommendations`, `recovery_plans`, `recovery_tasks`, `appointments`, `notifications`, `student_context`
- `mentorships` / sessions / messages when the mentorship schema and a staff mentor exist (`kind` separates mentoring vs counselling)
- `communities` slugs `demo-coding-club`, `demo-sports-circle`, `demo-cultural-circle`, `demo-academic-study`, `demo-campus-activities`, `demo-festive-committee` plus members/posts
- `reward_achievements`, `reward_transactions`, badges/milestones via existing reward helpers; `campus_merchants` Demo Campus Canteen
- `student_academic_outcomes` with `recorded_by=demo_seed`
- `complaints` / `student_appeals` / `student_moderation_status` for the Tara prototype path
- `staff_users` usernames `DEMO_*` and teacher `DEMO_FACULTY_01`

Not seeded: face/voice embeddings, live recognition results, performance-ML training rows, or fabricated dropout-rate rankings.

---

## How the app reads students for ML

Face SVM training selects `student_id, face_embedding` only (`get_all_students("student_id, face_embedding")`).  
Directory and FaceID roster select `student_id, name` so embeddings are not pulled into those JSON responses.
