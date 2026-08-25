# CLASSORA HTTP API

Base URL locally: `http://127.0.0.1:8000`.  
The Vite app calls the same paths (`/api/...`). In production the browser uses `VITE_API_URL` as the origin.

Unless noted, authenticated routes expect:

```http
Authorization: Bearer <session-token>
```

JSON bodies unless the row says `multipart`. Errors return `{ "detail": "..." }` with 4xx/5xx.

---

## Health

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/health` | No | `{ ok, ui: "react", supabase, face_models_ready, voice_models_ready, models }` |

---

## Session

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/me` | Yes | Current session payload (no passwords/embeddings) |

Auth responses typically return `{ token, session }`.

---

## Teacher auth and account

| Method | Path | Auth | Body / notes |
| --- | --- | --- | --- |
| POST | `/api/auth/teacher/login` | No | `{ username, password }` |
| POST | `/api/auth/teacher/register` | No | `{ username, password, name }` |
| POST | `/api/auth/teacher/forgot` | No | `{ username, registered_name, new_password, confirm_password }` |
| POST | `/api/auth/teacher/activate` | No | `{ username, token, password, confirm_password }` invite activation |
| POST | `/api/teacher/password` | Teacher | `{ current_password, new_password, confirm_password }` |
| POST | `/api/teacher/invites` | Teacher | `{ invited_name, invited_username }` returns plaintext token once |
| GET | `/api/teacher/invites` | Teacher | Invite list |
| GET | `/api/teacher/login-history` | Teacher | Recent `auth_events` |

---

## Staff auth

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/staff/login` | No | `{ username, password }` |
| POST | `/api/auth/staff/register` | No | `{ username, password, name, role }` role in `administrator`, `counsellor`, `faculty`, `mentor` |
| POST | `/api/staff/invite` | Administrator | `{ invited_name, invited_username, role }` |

---

## Student auth

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/api/auth/student/register` | No | `multipart`: `name`, `face`, optional `voice`. Face embedding stored immediately; voice processed in a background task |
| POST | `/api/auth/student/face` | No | `multipart`: `face`. Requires exactly one face. `{ matched, token?, session?, detail? }` |

---

## Teacher classroom

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/teacher/subjects` | Teacher | Subjects with enrollment counts |
| POST | `/api/teacher/subjects` | Teacher | `{ subject_code, name, section }` |
| GET | `/api/teacher/share/{subject_code}` | Teacher | `{ join_url, message }` |
| GET | `/api/teacher/attendance` | Teacher | Attendance rows for the teacher’s subjects |
| GET | `/api/teacher/institution` | Teacher | Filtered metrics + watchlist bundle |
| POST | `/api/teacher/attendance/face` | Teacher | `multipart`: `subject_id`, `photos[]` → present/absent ids |
| POST | `/api/teacher/attendance/voice` | Teacher | `multipart`: `subject_id`, `audio` |
| POST | `/api/teacher/attendance/confirm` | Teacher | `{ subject_id, present_ids, absent_ids }` writes `attendance_logs` |

---

## Student classroom

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/student/subjects` | Student | Enrolled subjects + related logs |
| POST | `/api/student/enroll` | Student | `{ subject_code }` |
| DELETE | `/api/student/subjects/{subject_id}` | Student | Unenroll |
| GET | `/api/student/risk` | Student | Snapshot + current risk widget payload |

---

## Student Success

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/success/hub` | Session | Ranked profiles + cases/recommendations |
| GET | `/api/success/student/{student_id}` | Session | Student 360 for that id in the loaded bundle |
| GET | `/api/success/workspace` | Session | Aggregated hub: modules, profiles, twins, alerts, mentorship, complaints, library |
| POST | `/api/success/help` | Student | `{ message }` queues in-app message |
| POST | `/api/success/appointment` | Student | `{ kind, starts_at? }` |
| POST | `/api/success/recommend` | Session | `{ student_id }` queues first library recommendation |
| POST | `/api/success/case` | Session | `{ student_id, intervention_name, notes?, priority? }` |
| POST | `/api/success/outcome` | Session | `{ student_id, result, notes? }` |
| POST | `/api/success/assistant` | Session | `{ question }` keyword replies only |

---

## Mentorship

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/mentorship` | Session | Student list / faculty caseload / admin overview |
| POST | `/api/mentorship/assign` | Session | `{ student_id, goal? }` |
| GET | `/api/mentorship/{mentorship_id}` | Session | One thread (aliases; identity stripped by role) |
| GET | `/api/mentorship/{mentorship_id}/messages` | Session | |
| POST | `/api/mentorship/{mentorship_id}/messages` | Session | `{ body }` |
| POST | `/api/mentorship/{mentorship_id}/sessions` | Session | `{ title, notes? }` |
| POST | `/api/mentorship/{mentorship_id}/feedback` | Session | `{ answers }` |
| POST | `/api/mentorship/{mentorship_id}/reassign` | Session | |
| POST | `/api/mentorship/{mentorship_id}/suspend` | Session | Admin/staff path as implemented in `mentorship.service` |

---

## Moderation

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| POST | `/api/moderation/complaints` | Session | Faculty/teacher/counsellor create; cannot execute ban |
| POST | `/api/moderation/appeals` | Session | Student appeal |
| POST | `/api/moderation/complaints/{complaint_id}/open` | Administrator | Move to review |
| POST | `/api/moderation/complaints/{complaint_id}/decide` | Administrator | `{ action, notes }` including ban/restrict when policy allows |

Ban/restrict authorization is enforced in `src/moderation/service.py` and `src/moderation/policy.py`, not by Postgres RLS.

---

## Academic resources

Any signed-in classroom role may **read**. Only **administrators** may create, edit, deactivate, verify, or review reports. Only **students** may report a broken link.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/academic-resources` | Session | Query: `year`, `semester`, `subject`, `type`, `source`, `search`, `sort`, `page`, `limit`. Server-side filter/search. Inactive rows hidden from non-admins |
| GET | `/api/academic-resources/catalog` | Session | Years, semesters, subjects, types, sources, formats. Seeds source/type catalog if empty |
| GET | `/api/academic-resources/{id}` | Session | One resource; original URL unchanged |
| POST | `/api/academic-resources` | Administrator | Create. HTTPS URL required. Duplicate subject+type+URL rejected |
| PUT | `/api/academic-resources/{id}` | Administrator | Edit metadata / URL / active flag |
| DELETE | `/api/academic-resources/{id}` | Administrator | Soft-deactivate (not a hard delete) |
| POST | `/api/academic-resources/{id}/verify` | Administrator | Sets `lastVerifiedAt` |
| POST | `/api/academic-resources/{id}/report` | Student | Broken-link report; one pending report per student+resource |
| GET | `/api/academic-years` | Session | Stable ids `YEAR_1`–`YEAR_4` |
| GET | `/api/academic-semesters` | Session | Optional `year`. Ids `SEM_1`–`SEM_8` |
| GET | `/api/academic-subjects` | Session | Optional `year`, `semester` |
| GET | `/api/academic-resource-types` | Session | Catalog-driven |
| GET | `/api/academic-sources` | Session | Seeded senior websites |
| POST | `/api/academic-subjects` | Administrator | |
| PUT | `/api/academic-subjects/{id}` | Administrator | |
| POST | `/api/academic-sources` | Administrator | |
| PUT | `/api/academic-sources/{id}` | Administrator | |
| POST | `/api/academic-resource-types` | Administrator | |
| GET | `/api/academic-resource-reports` | Administrator | Optional `status` |
| POST | `/api/academic-resource-reports/{id}/review` | Administrator | `{ decision: REVIEWED\|RESOLVED\|DISMISSED }` |

---

## Institutional anomalies

Authorized roles: **administrator**, **teacher**, **counsellor**. Students, faculty staff, and mentors cannot read these routes. Only administrator/teacher may analyze or change lifecycle. Only administrator may change thresholds.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/institutional-anomalies` | Authorized staff | Query: `severity`, `status`, `section`, `semester`, `course`, `metric`, `cohort_type`, `search`, `sort`, `start`, `end` |
| GET | `/api/institutional-anomalies/summary` | Authorized staff | Overview counts from stored events |
| GET | `/api/institutional-anomalies/settings` | Authorized staff | Thresholds + last analysis |
| PUT | `/api/institutional-anomalies/settings` | Administrator | Configurable min cohort, score, affected %, windows |
| POST | `/api/institutional-anomalies/analyze` | Administrator or teacher | Recomputes aggregates vs baseline; idempotent for the same window |
| GET | `/api/institutional-anomalies/{id}` | Authorized staff | Detail + hypotheses + hierarchy |
| GET | `/api/institutional-anomalies/{id}/timeline` | Authorized staff | Snapshot series |
| GET | `/api/institutional-anomalies/{id}/evidence` | Authorized staff | Explanation + metric evidence |
| GET | `/api/institutional-anomalies/{id}/cohort` | Authorized staff | Aggregate impact; student IDs only for administrators |
| POST | `/api/institutional-anomalies/{id}/acknowledge` | Administrator or teacher | |
| POST | `/api/institutional-anomalies/{id}/investigate` | Administrator or teacher | |
| POST | `/api/institutional-anomalies/{id}/resolve` | Administrator or teacher | |
| POST | `/api/institutional-anomalies/{id}/dismiss` | Administrator or teacher | |
| POST | `/api/institutional-anomalies/{id}/notes` | Administrator or teacher | `{ note }` |
| GET | `/api/institutional-anomalies/{id}/notes` | Authorized staff | |

---

## Institutional dropout root-cause

Authorized roles: **administrator** (institution-wide; DEAN/DIRECTOR equivalent) and **teacher** (HOD-equivalent, scoped to taught sections/courses). Students, counsellors, faculty staff, and mentors receive 403. Every route enforces RBAC server-side and writes an `audit_events` row without student names.

Dropout is taken only from `student_academic_outcomes`. There is no department table; `/departments` returns section aggregates plus an unavailable note.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/institutional-dropout/overview` | Admin or teacher | Cards, story, unavailable factors |
| GET | `/api/institutional-dropout/summary` | Admin or teacher | Cheap workspace summary |
| GET | `/api/institutional-dropout/settings` | Admin or teacher | Thresholds + last analysis |
| PUT | `/api/institutional-dropout/settings` | Administrator | Configurable sample-size and bands |
| POST | `/api/institutional-dropout/analyze` | Admin or teacher | Recomputes and upserts `default\|dropout-root-v1.0\|current` |
| GET | `/api/institutional-dropout/trends` | Admin or teacher | Period dropout rates |
| GET | `/api/institutional-dropout/factors` | Admin or teacher | Query: `factor`, `classification`, `confidence` |
| GET | `/api/institutional-dropout/factors/{id}` | Admin or teacher | Evidence, RR, RD, drill-down |
| GET | `/api/institutional-dropout/departments` | Admin or teacher | Sections + department-unavailable note |
| GET | `/api/institutional-dropout/departments/{id}` | Admin or teacher | One section slice |
| GET | `/api/institutional-dropout/semesters` | Admin or teacher | |
| GET | `/api/institutional-dropout/courses` | Admin or teacher | |
| GET | `/api/institutional-dropout/heatmap` | Admin or teacher | Section × semester |
| GET | `/api/institutional-dropout/intersections` | Admin or teacher | Combined-factor associations |
| GET | `/api/institutional-dropout/recommendations` | Admin or teacher | Decision-support only |
| GET | `/api/institutional-dropout/compare` | Admin or teacher | Query: `kind`, `left`, `right` |
| GET | `/api/institutional-dropout/report` | Admin or teacher | Aggregated report JSON |
| GET | `/api/institutional-dropout/export` | Admin or teacher | CSV |
| GET | `/api/institutional-dropout/first-year` | Admin or teacher | Early-semester concentration when labels exist |
| GET | `/api/institutional-dropout/outcomes` | Administrator | student_id + status only |
| POST | `/api/institutional-dropout/outcomes` | Administrator | Record an explicit outcome |
| POST | `/api/institutional-dropout/outcomes/import` | Administrator | CSV import |

### CLASSORA Rewards

Points are calculated on the server from `reward_policies`. Clients cannot submit a balance or a trusted discount. Redemption is a two-step validate → confirm. The QR/token payload is a random redemption identifier, not student marks or counselling data.

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| POST | `/api/rewards/merchant/login` | Public | Merchant ID + access code → merchant session |
| GET | `/api/rewards/wallet` | Student (own) or staff (`student_id`) | Server-derived wallet |
| GET | `/api/rewards/transactions` | Student / staff | Paginated ledger |
| GET | `/api/rewards/achievements` | Student / staff | Paginated achievements |
| POST | `/api/rewards/achievements` | Student or award staff | Student submissions stay pending |
| POST | `/api/rewards/awards` | Faculty / teacher / mentor / counsellor / admin | Policy-calculated recognition |
| POST | `/api/rewards/achievements/{id}/verify` | Verifier roles | Approve / reject / request changes |
| GET | `/api/rewards/requests` | Verifier roles | Pending verification and approval |
| POST | `/api/rewards/requests/{id}/approve` | Approver / verifier | Self-approval blocked by default |
| POST | `/api/rewards/requests/{id}/reject` | Verifier roles | Reason required |
| POST | `/api/rewards/transactions/{id}/reverse` | Administrator | Compensating `REVERSAL` row |
| POST | `/api/rewards/adjustments` | Administrator | Reason required |
| GET | `/api/rewards/recommend` | Award staff | Policy recommendation only |
| GET | `/api/rewards/rules` | Any reward viewer | How-to-earn copy |
| GET/PUT | `/api/rewards/settings` | Administrator | Feature flags and caps |
| GET/POST | `/api/rewards/policies` | GET viewers; POST admin | Versioned rules |
| GET | `/api/rewards/marketplace` | Reward viewers | Active offers |
| POST | `/api/rewards/offers/{id}/claim` | Student | Atomic deduct + voucher + token |
| GET | `/api/rewards/vouchers` | Student (own) / merchant (own outlet) | Token shown only at claim |
| POST | `/api/rewards/vouchers/{id}/cancel` | Administrator | Optional `REFUND` |
| POST | `/api/rewards/redemptions/validate` | Merchant / admin | Does not redeem |
| POST | `/api/rewards/redemptions/confirm` | Merchant / admin | Atomic `ACTIVE` → `REDEEMED` |
| GET/POST | `/api/rewards/merchants` | GET viewers; POST admin | Access code hashed |
| POST | `/api/rewards/offers` | Administrator | Inventory limits |
| GET | `/api/rewards/analytics` | Admin or teacher | Observed activity only |
| GET | `/api/rewards/leaderboard` | Viewers | Disabled unless configured |
| GET | `/api/rewards/reconcile` | Administrator | Ledger / voucher consistency |
| POST | `/api/rewards/jobs/tick` | Administrator | Expiry + reminders + optional attendance improvement |

Merchant tokens cannot load `/api/success/workspace`, academic resources, or dropout APIs.

### Secure multi-layer attendance

Existing `POST /api/teacher/attendance/face|voice|confirm` is unchanged (preview + faculty save). The routes below add session + student verification. Face match never writes `PRESENT` unless an administrator has explicitly enabled `FACE_ONLY` and faculty finalizes matched students.

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| POST | `/api/attendance/sessions` | Teacher | Start a time-boxed session |
| GET | `/api/attendance/sessions` | Teacher / admin | Recent sessions |
| GET | `/api/attendance/sessions/{id}` | Teacher (own) / admin | Live counts + roster states |
| POST | `/api/attendance/sessions/{id}/analyze` | Teacher | Classroom photos → existing dlib pipeline |
| POST | `/api/attendance/sessions/{id}/complete` | Teacher | Expires unverified marks; they are not present |
| POST | `/api/attendance/sessions/{id}/cancel` | Teacher / admin | Reason required |
| POST | `/api/attendance/sessions/{id}/finalize-matched` | Teacher | Only if policy is `FACE_ONLY` |
| POST | `/api/attendance/sessions/{id}/correction` | Teacher / admin | PRESENT / ABSENT / REJECT + reason + audit |
| GET | `/api/attendance/student/pending` | Student | Own verification requests only |
| GET | `/api/attendance/student/history` | Student | Own verified/manual history |
| POST | `/api/attendance/verification/qr` | Student | Rotating short-lived token |
| POST | `/api/attendance/verification/code` | Student | One-time hashed code |
| POST | `/api/attendance/verification/confirm` | Student | Token/code + optional device; atomic present |
| POST | `/api/attendance/device/register` | Student | Device secret issued once |
| GET/PUT | `/api/attendance/settings` | GET teacher/admin; PUT admin | Verification policy |
| GET | `/api/attendance/analytics` | Teacher / admin | Verified vs manual; pending not present |

### Predictive Intelligence

Statistical and retrieval-style analysis of uploaded academic/career text. There is no generative model and no vector database. Official schedules override date windows. Current syllabus down-ranks topics that no longer appear. Insufficient history returns an explicit insufficient status instead of a fabricated ranking. `student_id` on write is taken from the session, not the client.

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| GET | `/api/predictions/overview` | Student / staff | Counts, modes, capabilities (PDF/DOCX/OCR honesty) |
| GET/POST | `/api/predictions/documents` | Student (own + institution) / staff (institution) | Paste text. Duplicate content hash is reported |
| POST | `/api/predictions/documents/upload` | Same | TXT/CSV/MD/JSON; PDF/DOCX if libraries are installed. Images and executables rejected |
| GET/PATCH/DELETE | `/api/predictions/documents/{id}` | Owner or institution staff | Students cannot read another student's private text |
| POST | `/api/predictions/documents/{id}/reprocess` | Owner / staff | Rebuild items from stored text |
| POST | `/api/predictions/analyze` | Viewers | Academic + career + plan in one payload |
| GET | `/api/predictions/academic` | Viewers | Topic/question priorities |
| GET | `/api/predictions/exam-date` | Viewers | Window or official override |
| GET | `/api/predictions/questions` | Viewers | Ranked questions with evidence |
| GET | `/api/predictions/topics` | Viewers | Topic weightage |
| GET | `/api/predictions/career` | Viewers | Skills, rounds, stipend only if numbers exist |
| POST | `/api/predictions/query` | Viewers | Natural-language router over the same statistics |
| GET | `/api/predictions/history` | Student (own) / staff (non-student institutional) | Previous predictions |
| GET | `/api/predictions/evidence/{id}` | Viewers | Citations the caller is allowed to see |
| POST | `/api/predictions/plans` | Student | Save an edited study plan |
| GET/PUT | `/api/predictions/settings` | Administrator | Weights and minimum sample sizes |

### Final-score forecast (public benchmark)

Isolated from the PYQ Predictive Intelligence engine. Uses the trained `src/performance_ml` artifact. Not institutional data.

| Method | Path | Auth | Notes |
| --- | --- | --- | --- |
| GET | `/api/performance/model` | Student / staff | Dataset name, row count, target, features, MAE/RMSE/R², training timestamp |
| GET | `/api/performance/mapping` | Student (own) / staff (`student_id` required) | Which CLASSORA fields mapped; missing stay unavailable |
| POST | `/api/performance/predict` | Student (own) / staff (`student_id` required) | Body `{ student_id?, features?, mode? }`. `mode` is `benchmark` (public CSV) or `calibration` (synthetic demo). Returns predicted Final_Score, band, important factors, `synthetic` flag. Failures return 503 `Prediction temporarily unavailable.` |

Merchant sessions cannot call these routes.

### Communities

Students browse and join approved interest communities. New communities are requests until an administrator approves them. Duplicate/similar names are flagged, not auto-created. The default public identity is numeric `student_id`. Optional name/bio/skills are omitted from JSON unless that student enabled the matching privacy flag.

| Method | Path | Who | Notes |
| --- | --- | --- | --- |
| GET | `/api/communities` | Student / admin | Server-side search, category, pagination |
| GET | `/api/communities/{id}` | Student / admin | Detail; suspended communities are not in discovery |
| POST/DELETE | `/api/communities/{id}/join` `/leave` | Student | Unique membership |
| GET/POST | `/api/communities/{id}/posts` | Members post | Author identity resolved server-side |
| POST | `/api/communities/requests` | Student | Preview/block on near-duplicates; `continueDespiteDuplicates` flags admin |
| POST | `/api/communities/requests/{id}/review` | Administrator | APPROVE / REJECT / CHANGES |
| GET/PUT | `/api/communities/privacy` | Student (own) | `studentId` in the body cannot change another student |
| POST | `/api/communities/reports` | Student | Moderators/admin resolve |
| GET | `/api/community-reports` | Admin / community moderators | Open reports |
| POST | `/api/communities/{id}/status` | Administrator | ACTIVE / SUSPENDED / ARCHIVED |

No direct messaging. Merchant sessions cannot call these routes.

---

## OpenAPI

With the API running: http://127.0.0.1:8000/docs (FastAPI Swagger UI) and `/redoc`.
