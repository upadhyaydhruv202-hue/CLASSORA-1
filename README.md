# CLASSORA

**Intelligent Learning. Connected Classrooms.**

CLASSORA is an AI attendance and student-success platform for classrooms. Teachers capture class photos or a short voice recording; the system matches enrolled students, writes attendance, and then scores support-risk from those records. Students sign in with FaceID. Counsellors and staff review explanations, open cases, assign anonymous mentorship, and handle complaints — with a human in the loop.

This repository is the complete working source: FastAPI backend, React frontend, SQL schemas, and ML pipelines.

| Layer | Live deployment |
| --- | --- |
| Website | https://classora-six.vercel.app |
| API | https://classora-production.up.railway.app/api/health |

---

## Project Objective

CLASSORA exists to replace paper registers and opaque “AI risk” dashboards with a single classroom workflow:

1. **Mark who was present** using face and optional voice recognition against the enrolled roster.
2. **Explain attendance-driven risk** with a deterministic, inspectable score — not a black-box diagnosis.
3. **Support the student** through human-reviewed interventions, mentorship, and moderation.

**Problem.** Manual attendance is slow and easy to game. Early-warning tools often hide how a score was produced, or they automate interventions. Institutions need identity-based attendance plus explainable support signals that a counsellor can override.

**Primary goal.** Detect presence, persist it, and turn that history into an explainable support picture that staff act on.

**Intended users**

| Role | Use |
| --- | --- |
| Student | FaceID login, subject enrollment, own attendance and risk view, mentorship, help requests |
| Teacher | Subjects, face/voice attendance, records, institution snapshot, Success Hub |
| Counsellor / faculty / mentor | Caseload, Digital Twin, recommendations, cases, anonymous mentorship |
| Administrator | Staff invites, mentorship admin, complaint review and bans |

---

## Key Features

### Fully implemented

- **Marketing landing (`/`)** — cinematic Three.js/React experience with Launch CLASSORA → `/app`
- **Classroom app (`/app`)** — student, teacher, and staff portals
- **Teacher register / login** — bcrypt passwords, invite tokens, forgot-password + activate, login history
- **Student FaceID register and login** — dlib 128-d embeddings; optional voice enrollment in the background
- **Staff register / login** — administrator, counsellor, faculty, mentor
- **Subjects and enrollment** — create subjects, share join codes, enroll / unenroll
- **Face attendance** — classroom photos → present / absent roster → confirm write to `attendance_logs`
- **Voice attendance** — Resemblyzer embeddings against enrolled voice profiles
- **HMAC session tokens** — role + ids only; passwords and embeddings are stripped
- **Student Success Hub** — risk score, Digital Twin, explanations, recovery/what-if, trajectory
- **Human-in-the-loop interventions** — recommend, open case, record outcome, appointments, in-app help
- **Anonymous mentorship** — assign, messages, sessions, feedback, reassign, suspend
- **Moderation** — faculty/teacher complaints; administrator review, decide, student appeals
- **Local fallback store** — `data/local_db.json` when Supabase is not configured
- **Production deploy** — Vercel (frontend) + Railway (API)

### Partially implemented

- **Academic records / LMS events** — PostgreSQL tables and Success Hub tables exist; there is no LMS connector and no dedicated grade-entry UI. Risk uses these rows when they are present.
- **Reports / Search / Import / Settings / Faculty portal / Ecosystem analytics** — workspace tabs exist and show live profile metrics; they are not separate export, search, or LMS-import products.
- **In-app assistant** — keyword replies from attendance/twin/tasks, not a generative LLM.
- **Row Level Security** — enabled on tables, but current policies allow `anon` full access (typical student-project pattern). Production hardening is not done.

### Planned / not implemented

- Native Moodle / Canvas / Google Classroom sync
- Automatic interventions without a human reviewer
- SHAP/LIME black-box explainers (the risk model is additive and already explained in-code)
- Streamlit UI (removed; FastAPI + React only)
- Demo / guest accounts (removed from the running app)

---

## Technology Stack

| Area | Actual stack |
| --- | --- |
| Frontend | React 19, Vite 8, Tailwind CSS 4, Framer Motion, Three.js, React Three Fiber / Drei |
| Classroom UI | React (`website/src/classroom/`) |
| Backend | Python 3.11, FastAPI, Uvicorn, Python-Multipart, Pillow |
| Auth | Custom HMAC-signed tokens (`src/auth/tokens.py`), bcrypt password hashes |
| Database | Supabase PostgreSQL (optional); JSON file store when unset |
| Face ML | dlib HOG detector, `face_recognition_models` shape + 128-d ResNet, scikit-learn linear SVM |
| Voice ML | librosa, Resemblyzer (`VoiceEncoder`) |
| Success ML | Deterministic Python scorer `success-risk-v1.1` (not a trained neural net) |
| Tests | Python `unittest` (`tests/`) |
| Deploy | Vercel (Vite site), Railway / Nixpacks (API), Procfile for process start |
| External | Supabase API, Google Fonts (landing) |

---

## Current Implementation Status

| Component | Status | Details |
| --- | --- | --- |
| Frontend | Complete | Landing + `/app` portals, camera, mic, Success Hub charts/tables |
| Backend | Complete | FastAPI in `src/api/app.py` + `src/api/features.py` |
| Database | Complete | SQL in `supabase/`; local JSON fallback without cloud keys |
| Authentication | Complete | Teacher/staff passwords, student FaceID, HMAC sessions, RBAC |
| AI/ML | Complete (attendance); Partial (LMS/academics) | Face/voice pipelines run in production; risk uses attendance always and academics/LMS only if rows exist |
| Major features | Complete | Attendance, enrollment, success hub, mentorship, moderation |
| Hub utility tabs | Partial | Reports/Search/Import/Settings are live summary views, not full products |
| Deployment | Complete | Vercel + Railway, CORS for `*.vercel.app` |
| Tests | Partial | Policy, risk widget, and explanation/twin unit tests; no full E2E suite |

---

## Repository layout

Source stays at the repository root so `uvicorn main:app` and the Vite/Vercel configs keep working. Detailed docs are under `documentation/`.

```text
.
├── README.md                 # This file
├── .env.example              # API secrets template (no real keys)
├── .gitignore
├── documentation/            # Architecture, API, database
├── src/                      # Backend, auth, DB, ML pipelines
│   ├── api/                  # FastAPI app + Success/mentorship/moderation routes
│   ├── auth/                 # Tokens, RBAC, session sanitization
│   ├── database/             # Supabase client + local JSON store
│   ├── pipelines/            # Face + voice
│   ├── success/              # Risk model, twin, intelligence
│   ├── mentorship/
│   └── moderation/
├── website/                  # React SPA (landing + /app)
├── supabase/                 # PostgreSQL schemas
├── tests/
├── main.py                   # API entry: loads .env, exports FastAPI app
├── requirements.txt
├── railway.toml
├── nixpacks.toml             # Python 3.11 + ffmpeg/libsndfile
└── Procfile
```

---

## Setup / Installation

### 1. Prerequisites

- **Python 3.11** (required for `dlib-bin`; 3.13 is not supported here)
- **Node.js 20+** and npm
- **Git**
- Optional for voice: FFmpeg / libsndfile (Railway image already includes them)
- Optional for cloud data: a [Supabase](https://supabase.com) project

Windows (this project’s development OS):

```powershell
py -3.11 --version
node --version
```

### 2. Clone

```bash
git clone <your-fork-or-repo-url>
cd ai-attendance-pipelines
```

### 3. Backend dependencies

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

macOS / Linux:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

`requirements.txt` installs FastAPI, dlib, face-recognition models (GitHub), scikit-learn, librosa, Resemblyzer, Supabase, bcrypt, and related packages. First install can take several minutes.

### 4. Environment variables

```powershell
copy .env.example .env
```

Edit `.env`:

| Variable | Required | Purpose |
| --- | --- | --- |
| `SUPABASE_URL` | For cloud DB | Project URL |
| `SUPABASE_KEY` | For cloud DB | Anon or service key — **never commit it** |
| `SESSION_SECRET` | Production | Signing key for session tokens |
| `APP_URL` | CORS | `http://localhost:5173` locally |

Leave `SUPABASE_URL` and `SUPABASE_KEY` blank to run against `data/local_db.json` (created automatically; `data/` is gitignored).

Frontend (only if you are not using the Vite `/api` proxy):

```powershell
copy website\.env.example website\.env.local
```

Keep `VITE_API_URL` empty locally. Vite proxies `/api` → `http://127.0.0.1:8000`.

### 5. Database configuration

If using Supabase, open **SQL Editor** and run in this order:

1. `supabase/schema.sql` — teachers, students, subjects, enrollment, attendance, auth events, teacher invites
2. `supabase/schema_auth.sql` — additive auth tables (safe if already in step 1)
3. `supabase/schema_success.sql` — staff, academics, LMS events, risk, cases, appointments
4. `supabase/schema_mentorship.sql` — anonymous mentorship
5. `supabase/schema_moderation.sql` — complaints, appeals, student status

There is no ORM migration runner. There is no seed script for production. Register users through `/app`.

### 6. AI / ML setup

No extra model files to download. Pip installs:

- dlib detector + `face_recognition_models` `.dat` files
- Resemblyzer weights on first voice request (Torch)

The API preloads dlib (and the face SVM when students exist) at process start.

### 7. Start the API

```powershell
py -3.11 -m uvicorn main:app --host 127.0.0.1 --port 8000
```

Health: http://127.0.0.1:8000/api/health

### 8. Start the frontend

```powershell
cd website
npm install
npm run dev
```

| URL | What opens |
| --- | --- |
| http://localhost:5173/ | Marketing landing |
| http://localhost:5173/app | Classroom portals |
| http://127.0.0.1:8000/api/health | API health JSON |

### 9. Tests

```powershell
py -3.11 -m unittest discover -s tests -v
```

Covers moderation policy, risk widget mapping, and Digital Twin / explanation payloads. Not a substitute for a full browser E2E pass.

### 10. Production build (frontend)

```powershell
cd website
npm run build
npm run preview
```

Set `VITE_API_URL` at **build time** to the public API origin (see `website/.env.production` on the deploy machine, not in git).

---

## Deployment

**API (Railway)** — `railway.toml` starts `uvicorn main:app --host 0.0.0.0 --port $PORT`, health check `/api/health`, Python 3.11 via `nixpacks.toml`. Set `SUPABASE_URL`, `SUPABASE_KEY`, `SESSION_SECRET`, and `APP_URL` (Vercel origin) in the Railway service. `sleepApplication` is off on the current service.

**Website (Vercel)** — `website/vercel.json` builds Vite and rewrites all routes to `index.html`. Set `VITE_API_URL` to the Railway origin. CORS in `src/api/app.py` allows localhost, `APP_URL`, and `https://*.vercel.app`.

---

## Documentation

| Document | Contents |
| --- | --- |
| [documentation/PROJECT.md](documentation/PROJECT.md) | Overview, architecture, workflows, roles, ML, configuration, future work |
| [documentation/API.md](documentation/API.md) | HTTP routes as implemented |
| [documentation/DATABASE.md](documentation/DATABASE.md) | Tables and how they are used |

---

## Security notes for reviewers

- `.env` and `.streamlit/secrets.toml` are gitignored. Do not paste keys into issues or the README.
- Session tokens do not include passwords or embeddings.
- Current Supabase RLS policies are open to `anon` for this hackathon-style client. Do not treat that as production-grade multi-tenant isolation.
- Predicted risk is a **support signal**, not a diagnosis. Interventions are created only after a staff action.

---

## License

Apache License 2.0. See [LICENSE](LICENSE).
