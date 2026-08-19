# CLASSORA — Project documentation

This document matches the implementation in this repository: FastAPI (`main.py` → `src/api/app.py`), React/Vite (`website/`), PostgreSQL schemas (`supabase/`), and the face / voice / risk pipelines under `src/`.

---

## 1. Project overview

CLASSORA is a classroom product with two surfaces in one SPA:

| Path | Code | Purpose |
| --- | --- | --- |
| `/` | `website/src/experience/` | Marketing landing (Three.js scene + overlays) |
| `/app` | `website/src/classroom/` | Working product: auth, attendance, Success Hub |

The API is a single FastAPI app. It talks to **Supabase PostgreSQL** when `SUPABASE_URL` and `SUPABASE_KEY` are set; otherwise it uses **`data/local_db.json`**. Face recognition uses dlib embeddings and a linear SVM. Voice uses Resemblyzer. Student-success risk is a **deterministic Python scorer** (`success-risk-v1.1`) isolated from the face/voice modules.

The live stack used in development and deploy: **Vercel** for the site, **Railway** for the API, **Supabase** for the shared database.

---

## 2. Problem statement

Taking attendance on paper or a roll-call app does not create a durable identity signal. Institutions that add “AI dropout prediction” often cannot show *why* a student was flagged, and some tools trigger interventions automatically.

CLASSORA targets three gaps together:

- **Who was in the room** — match faces (and optionally voices) to enrolled students.
- **What the history implies** — attendance streaks, sudden decline, and optional academic/LMS rows into an inspectable score.
- **Who decides** — counsellors open cases; administrators alone execute bans; the in-app copy states that predicted risk is not a diagnosis.

---

## 3. Project objective

Ship a usable classroom loop:

1. Teachers create subjects and share a join code.
2. Students register a face (optional voice) and enroll.
3. Teachers capture photos or audio; the API returns present/absent; the teacher confirms.
4. The Success Hub scores enrolled students, explains drivers, and lets staff assign mentorship or file complaints.

Intended setting: a college or school classroom with a laptop/phone camera, not a nationwide SIS replacement.

---

## 4. System architecture

```text
Browser (Vite / Vercel)
  /                 cinematic landing
  /app              classroom SPA
        │
        │  fetch  (dev: Vite proxy /api → :8000)
        │  prod: VITE_API_URL → Railway
        ▼
FastAPI  (Uvicorn, Python 3.11)
  src/api/app.py         health, auth, attendance, enroll
  src/api/features.py    password, invites, workspace, mentorship, moderation
        │
        ├── src/pipelines/face_pipeline.py     dlib + SVM
        ├── src/pipelines/voice_pipeline.py    Resemblyzer
        ├── src/success/risk_model.py          success-risk-v1.1
        ├── src/mentorship/service.py
        ├── src/moderation/service.py
        └── src/database/
              config.py     env + optional .streamlit/secrets.toml
              db.py         Supabase table helpers
              local_store.py  JSON fallback
        ▼
Supabase PostgreSQL   or   data/local_db.json (+ data/success_store.json)
```

**Request auth.** The SPA stores a signed token in `localStorage` (`classora_token`) and sends `Authorization: Bearer …`. `src/auth/tokens.py` HMAC-SHA256 signs a payload of role and public profile fields. Demo-mode tokens are rejected (`src/api/deps.py`).

**CORS.** Local Vite origins, `APP_URL`, and `https://*.vercel.app`.

**Unused frontend files.** `website/src/components/` is leftover marketing markup and is **not** mounted by `website/src/App.jsx`. The live landing is `experience/`.

---

## 5. Major modules / components

### Frontend

| Module | Path | What it does |
| --- | --- | --- |
| App shell | `website/src/App.jsx` | `/` vs `/app`; landing splash once per session |
| Landing | `website/src/experience/` | 3D world, overlays, Launch CLASSORA |
| Classroom | `website/src/classroom/App.jsx` | Portals, auth, teacher desk, student desk, staff hub |
| Camera | `CameraCapture.jsx` | JPEG capture (640px face, 960px classroom) |
| Mic | `MicRecorder.jsx` | Voice enrollment / attendance |
| Success UI | `Features.jsx` | Workspace modules, twin charts, mentorship, complaints |
| API client | `api.js` | All HTTP calls; prefixes `VITE_API_URL` |

### Backend

| Module | Path | What it does |
| --- | --- | --- |
| App | `src/api/app.py` | Core REST + lifespan preload of dlib / SVM |
| Features router | `src/api/features.py` | Teacher account extras + full Success workspace payload |
| Face | `src/pipelines/face_pipeline.py` | Shrink image, detect, 128-d embedding, SVM match |
| Voice | `src/pipelines/voice_pipeline.py` | Encoder + cosine match / bulk segments |
| Intelligence | `src/success/intelligence.py` | Assemble students, logs, academics, LMS into profiles |
| Risk | `src/success/risk_model.py` | Features, score, explain, recovery, trajectory |
| Twin | `src/success/twin.py` | Staff/student Digital Twin payload |
| Store | `src/success/store.py` | Insert/select success tables (cloud or JSON) |
| Mentorship | `src/mentorship/` | Lifecycle, aliases, messages |
| Moderation | `src/moderation/` | Complaints, admin decide, login gates |
| RBAC | `src/auth/rbac.py` | Role permission map used by guards |

---

## 6. Application workflow

### Teacher attendance

1. Register or log in (`/api/auth/teacher/*`).
2. Create a subject (`POST /api/teacher/subjects`).
3. Share join code (`GET /api/teacher/share/{subject_code}` → `/app?join-code=…`).
4. Capture one or more classroom photos; `POST /api/teacher/attendance/face` runs `predict_attendance` per image.
5. Review present/absent names; `POST /api/teacher/attendance/confirm` writes `attendance_logs`.
6. Optional: `POST /api/teacher/attendance/voice` with a room recording.

### Student

1. Capture face → `POST /api/auth/student/face`. Unmatched faces are told to register.
2. Register name + face (`POST /api/auth/student/register`). Voice bytes, if any, are embedded **after** the response (`BackgroundTasks`).
3. Enroll with subject code (`POST /api/student/enroll`).
4. View subjects, attendance-derived risk, Digital Twin, mentorship, account/moderation snapshot.

### Staff / Success Hub

1. Staff register/login (`/api/auth/staff/*`).
2. `GET /api/success/workspace` returns role-specific module names, profiles, twins, cases, mentorship, complaints.
3. Recommend → human review → open case → record outcome.
4. Assign anonymous mentorship; student and mentor chat under aliases until policy reveals identity.
5. Faculty/teacher file complaints; **only administrator** executes restriction/ban.

Landing “AI Demo” sliders (`website/src/experience/predict.js`) are **illustrative** and do not write to the database.

---

## 7. User roles and permissions

Defined in `src/auth/rbac.py`. Route-level checks use `require_role(...)`.

| Role | Access in the running app |
| --- | --- |
| `teacher` | Own subjects, face/voice attendance, confirm logs, institution metrics, Success Hub, own complaints, invites, password change |
| `student` | Own subjects, enroll/unenroll, own risk/twin, help, appointments, mentorship, appeals |
| `counsellor` | Success Hub, 360, cases, mentorship assign, complaints (create, not execute ban) |
| `faculty` / `mentor` | Twin/explain/what-if, mentorship messages, report student |
| `administrator` | Staff invite, mentorship admin, complaint review, execute moderation actions, appeals |

**Login blockers.** `src/moderation/service.py` `login_allowed` can refuse a student whose moderation status is restricted / suspended / banned.

Passwords (teachers/staff): minimum 8 characters, at least one letter and one number (`password_strength`). Students have **no password**; identity is the face embedding.

Sessions expire after 60 minutes (`SESSION_MINUTES` in `src/auth/session.py`).

---

## 8. Database

See [DATABASE.md](DATABASE.md). Summary:

- **Core classroom:** `teachers`, `students` (JSON embeddings), `subjects`, `subject_students`, `attendance_logs`
- **Auth extras:** `auth_events`, `teacher_invites`
- **Success:** `staff_users`, academic/LMS/risk/cases/appointments, etc.
- **Mentorship / moderation:** additive schemas; run after success SQL

Without Supabase, classroom data is `data/local_db.json`. Success-layer inserts that are not cloud-only go to `data/success_store.json`. Mentorship and complaints are **cloud-only** (`store._CLOUD_ONLY`).

---

## 9. API / backend architecture

See [API.md](API.md).

- Entry: `main.py` loads `.env` then imports `app`.
- Lifespan: load dlib models; fit face SVM from stored embeddings if any.
- Health: `GET /api/health` uses `importlib.util.find_spec` (does not import Torch).
- File uploads: `python-multipart` + Pillow → numpy RGB.
- Success workspace is one aggregated GET so the SPA is not chatty.

---

## 10. AI / ML workflow

### Face (attendance + FaceID)

1. Client sends a JPEG (resized in the browser).
2. Server converts to RGB, thumbnails to 640px (960px for class photos).
3. `dlib.get_frontal_face_detector()` with **upsample 0**.
4. Shape predictor + `face_recognition_model_v1` descriptor with **0 jitters** (128 floats).
5. **Register:** store embedding on `students`; invalidate SVM cache (refit on next login/attendance).
6. **Match:** linear `SVC` over stored embeddings; L2 distance ≤ 0.6 to accept. FaceID login also requires exactly one face in frame.

This is classical dlib + SVM, not a custom-trained CNN in this repo.

### Voice

1. librosa load at 16 kHz → Resemblyzer `embed_utterance`.
2. Identify by cosine similarity (threshold 0.65).
3. Bulk attendance splits silence with `librosa.effects.split`.

First voice call loads Torch + the encoder (slow). Face register does not wait on that.

### Success risk (`success-risk-v1.1`)

Implemented in `src/success/risk_model.py`. It does **not** import face/voice.

Inputs: attendance logs; optional `academic_records` and `lms_events`.

Outputs: score 0–100, category (e.g. Stable / High / Critical), confidence, missing-data flags, additive **contributors** (not SHAP), narrative “why”, recovery counterfactuals, trajectory.

Recommendations come from a static library (`DEFAULT_LIBRARY`) filtered by attendance/academic rules. Financial-support referral is marked `available: False` in that library.

Disclaimer string is returned to the UI: predicted risk is a support signal, not a diagnosis.

---

## 11. Important dependencies and external services

**Python (`requirements.txt`):** numpy, pandas, scikit-learn, dlib-bin, face_recognition_models (Git), supabase, bcrypt, librosa, resemblyzer, python-dotenv, fastapi, uvicorn, python-multipart, pillow, setuptools&lt;70.

**Node (`website/package.json`):** react 19, react-dom, vite 8, tailwindcss 4, framer-motion, three, @react-three/fiber, @react-three/drei, lucide-react.

**Services:** Supabase REST, optional production hosts Vercel and Railway. Landing fonts: Google Fonts.

**Not used in the running UI:** Streamlit (comment in requirements: “API (no Streamlit)”).

---

## 12. Configuration requirements

| Name | Where | Role |
| --- | --- | --- |
| `SUPABASE_URL` / `SUPABASE_KEY` | root `.env` or Railway | Cloud database |
| `SESSION_SECRET` | root `.env` or Railway | Token HMAC |
| `APP_URL` | root `.env` or Railway | CORS allowlist |
| `VITE_API_URL` | Vite env at **build** time | Absolute API origin in production |
| `VITE_APP_URL` | Vite env | Classroom path, default `/app` |

`src/database/config.py` also reads `.streamlit/secrets.toml` if present (legacy). Prefer `.env`. Never commit either file.

---

## 13. Deployment

| Piece | How it is deployed in this project |
| --- | --- |
| API | Railway Nixpacks, Python 3.11, `uvicorn main:app --host 0.0.0.0 --port $PORT`, health `/api/health` (300s timeout) |
| Web | Vercel project on `website/`, `npm run build`, SPA rewrite to `index.html` |
| Models | Installed in the API image; dlib weights via pip; Torch via Resemblyzer |

Current public URLs (may change if the team recreates projects):

- https://classora-six.vercel.app
- https://classora-production.up.railway.app/api/health

---

## 14. Future enhancements

These are **not** implemented:

- Tight RLS (per-teacher/per-student policies) instead of open `anon` policies
- Real LMS/SIS connectors and CSV import
- Full report export, global search, and settings consoles (tabs today are summary views)
- Generative counsellor assistant
- Face inference closer to the user (current API region is CPU on Railway)
- Removing unused `website/src/components/` marketing files
- Moving secrets off the anon key to a server-only service role

---

## 15. Tests

```text
tests/test_moderation_policy.py
tests/test_risk_widget.py
tests/test_risk_explain.py
```

`demo_data.py` is used by tests, not by the live `/app` login flow.
