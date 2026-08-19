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
| POST | `/api/auth/student/quick` | No | Query `student_id`. Directory shortcut login |
| GET | `/api/student/directory` | No | `{ student_id, name }[]` public names only |

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

## OpenAPI

With the API running: http://127.0.0.1:8000/docs (FastAPI Swagger UI) and `/redoc`.
