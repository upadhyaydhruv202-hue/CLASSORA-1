# CLASSORA demo dataset

**DEMO DATA — NOT REAL STUDENT DATA.**

Synthetic records for prototype demonstration. They are not institutional student files, not measured classroom speech, and not live FaceID matches.

## Commands

```powershell
py -3.11 scripts/seed_demo_data.py
py -3.11 scripts/seed_demo_data.py --reset
py -3.11 scripts/seed_demo_data.py --reset-and-seed
```

`--reset` deletes only rows labeled as demo (`(Demo)` names, `DEMO-*` subjects, `DEMO_*` staff, demo community slugs, Demo Campus Canteen). It does not delete other students or faculty.

Do not run `--reset` against a production roster unless you intend to remove the prototype dataset.

## Demo logins

Shared password for seeded staff / teacher / merchant: `DemoPass123`

| Username | Role | How to sign in |
|---|---|---|
| `DEMO_ADMIN` | administrator | Staff login |
| `DEMO_FACULTY_01` | teacher | Faculty/teacher login |
| `DEMO_FACULTY_STAFF` | faculty (staff) | Staff login |
| `DEMO_COUNSELLOR_01` | counsellor | Staff login |
| `DEMO_COUNSELLOR_02` | counsellor | Staff login |
| `DEMO_MENTOR_01` | mentor | Staff login |
| `DEMO_MENTOR_02` | mentor | Staff login |
| Demo Campus Canteen (Demo) | merchant | Merchant login with the printed merchant id + `DemoPass123` |

Students such as `Aarav Mehta (Demo)` are **roster records only**. CLASSORA student login is FaceID. Demo students have **no face/voice embeddings**. Enroll a real face on a demo student only if you intentionally want that camera path.

Operational demo students (12): Aarav, Diya, Kabir, Meera, Rohan, Ananya, Vihaan, Sara, Ishaan, Tara, Neil, Zara — all surnames are fictional and names end with `(Demo)`.

Historical outcome students (16): labeled `Historical … (Demo)` so dropout root-cause has explicit `ACTIVE` / `GRADUATED` / `WITHDRAWN` / `DROPPED_OUT` / `DISCONTINUED` rows. Total demo students: **28**.

## What is seeded

- 12 operational demo students + 16 historical outcome students (dropout RCA)
- `DEMO-*` subjects (including faculty `DEMO-CS201` / `DEMO-LAB201`), attendance logs, `Demo ·` academics, `DEMO-HUB` LMS events
- Separate **mentoring** (`kind=mentor`) and **counselling** (`kind=counsellor`) threads. Kabir and Vihaan have both when the hosted `mentorships` kind unique index is applied
- Communities in existing categories: Technical, Sports, Cultural, Academic, Activities, Festive
- Rewards, merchant offer, optional voucher for Aarav
- Alerts, cases, recovery tasks, appointments, notifications
- Prototype complaint (application-generated complaint code) + Tara **RESTRICTED** + reviewed appeal (`REJECTED`)
- Import fixtures in `scripts/demo_fixtures/` (valid / duplicate / invalid) plus two demo `import_jobs` rows
- Explicit academic outcomes in `student_academic_outcomes` (`recorded_by=demo_seed`)
- Seed invokes the **existing** dropout and cohort-anomaly analyzers so dashboards are not stuck on “no analysis has been run yet.” Rankings are not inserted by hand.

## Institution label

If Settings had no institution name, seed sets `CLASSORA DEMO UNIVERSITY`. An existing non-demo name is left unchanged.

## Still requires hardware or live action

- Student FaceID register/login
- Live classroom face/voice attendance capture
- Secure attendance QR / device capture
- Any workflow that must be performed through the camera or microphone

The performance-ML artifacts under `src/performance_ml/artifacts/` are a separate public-dataset model. Demo roster rows are not that training set.

## Judge walkthrough (existing UI)

1. Start API (`uvicorn` on port 8000) and website (`npm run dev`; often http://localhost:5174/app).
2. Staff login as `DEMO_ADMIN` / `DemoPass123` → Analytics, Reports, Search, Monitoring, Appeals, Complaints, Rewards, Dropout root cause, Anomalies, Settings.
3. Faculty login as `DEMO_FACULTY_01` / `DemoPass123` → subjects `DEMO-CS201` / `DEMO-LAB201`, roster, attendance history, Success Hub. Pick `Kabir Patel (Demo)` for a high-risk profile and `Aarav Mehta (Demo)` for a stable profile.
4. Counsellor login as `DEMO_COUNSELLOR_01` → counselling caseload. Mentoring accept is not a counsellor action.
5. Mentor login as `DEMO_MENTOR_01` → mentoring caseload. Counselling accept is not a mentor action.
6. Merchant login with the seeded canteen id + `DemoPass123` → offer / voucher.
7. Student FaceID is a live camera path. Do not expect demo roster names to sign in until a real face is enrolled.

Tara Bose (Demo) is **RESTRICTED** so the appeal workflow is visible. Do not FaceID-enroll Tara unless you want that restriction to apply to a live student session.
