import { useEffect, useMemo, useState } from "react";
import { api, clearSession, hasSession, saveSession } from "./api";
import CameraCapture from "./CameraCapture";
import MicRecorder from "./MicRecorder";
import { formatDateTime } from "./display";
import AcademicResources from "./AcademicResources";
import SuccessWorkspace, { AccountPanel, InstitutionPanel } from "./Features";
import ClassoraRewards from "./ClassoraRewards";
import SecureAttendance from "./SecureAttendance";
import Communities from "./Communities";
import {
  DashFooter,
  DashHeader,
  EmptyState,
  Field,
  HomeFooter,
  HomeHeader,
  Notice,
  RiskWidget,
  StretchNav,
  SubjectCard,
  WelcomeBanner,
} from "./ui";
import "./classora.css";

function joinCodeFromUrl() {
  return new URLSearchParams(window.location.search).get("join-code") || "";
}

const STUDENT_MODULES = [
  "Student snapshot",
  "My Digital Twin",
  "My Risk",
  "AI Explanation",
  "Recovery AI",
  "Future trajectory",
  "Interventions",
  "Notifications",
  "Ask for support",
  "Anonymous Mentorship",
  "Academic Resources",
  "My Rewards",
  "Verify Attendance",
  "Predictive Intelligence",
  "Communities",
  "Account",
];

function studentTabFromUrl() {
  const tab = new URLSearchParams(window.location.search).get("tab");
  if (["subjects", "progress", "resources", "mentorship", "rewards", "verify", "predict", "communities", "account"].includes(tab)) return tab;
  return "subjects";
}

function studentWorkspaceShell(session, riskPayload) {
  const student = session?.student_data || {};
  if (student.student_id == null) return null;
  const risk = riskPayload?.risk || {};
  const score = risk.riskScore ?? 0;
  const category = risk.modelCategory || "Stable";
  const pred = {
    score,
    category,
    widgetLevel: risk.riskLevel || "LOW",
    confidence: risk.confidence,
    drivers: risk.drivers || [],
    missing: risk.missing || [],
    disclaimer: risk.disclaimer || "Predicted risk is a support signal, not a diagnosis.",
    model_version: risk.modelVersion,
  };
  const profile = {
    student_id: student.student_id,
    name: student.name,
    courses: [],
    attendance: {},
    academic: {},
    engagement: {},
    prediction: pred,
    recommendations: risk.recommendations || [],
  };
  const twin = {
    studentId: student.student_id,
    displayName: student.name,
    disclaimer: pred.disclaimer,
    overview: {
      riskScore: score,
      category,
      widgetLevel: pred.widgetLevel,
      confidence: pred.confidence,
      status: category,
      temporal: {},
    },
    academic: {},
    attendance: {},
    engagement: {},
    risk: { score, category, drivers: pred.drivers, missing: pred.missing, why: {} },
    intervention: {},
    mentorship: { status: "NONE", active: false },
    recovery: { actions: risk.recommendations || [] },
    trajectory: {},
    timeline: [],
  };
  return {
    role: "student",
    modules: STUDENT_MODULES,
    profiles: [profile],
    twins: { [String(student.student_id)]: twin },
    mine: profile,
    risk,
    cases: [],
    recommendations: [],
    academic: [],
    lms: [],
    alerts: [],
    library: [],
    notifications: [],
    appointments: [],
    tasks: [],
    messages: [],
    mentorship: [],
    complaints: [],
    appeals: [],
    account: riskPayload?.snapshot || null,
    moderation_meta: { categories: [], severities: [], actions: [], execute_actions: [] },
    disclaimer: pred.disclaimer,
  };
}

const portals = [
  {
    id: "student",
    kicker: "STUDENT",
    title: "I'm a Student",
    body: "Sign in with FaceID, enroll in subjects, and track your attendance in a connected classroom.",
    cta: "Student Portal →",
  },
  {
    id: "teacher",
    kicker: "FACULTY",
    title: "I'm Faculty",
    body: "Run AI face & voice attendance, manage subjects, and review classroom records instantly.",
    cta: "Faculty Portal →",
  },
  {
    id: "staff",
    kicker: "STAFF",
    title: "Counsellor / Admin / Faculty",
    body: "Student Success Hub: predicted-risk review, cases, and interventions.",
    cta: "Staff Portal →",
  },
  {
    id: "merchant",
    kicker: "CAMPUS",
    title: "Campus Merchant",
    body: "Validate and redeem CLASSORA Reward vouchers for your outlet. You cannot see academic or counselling data.",
    cta: "Merchant Portal →",
    secondary: true,
  },
];

const teacherNav = [
  { id: "attendance", label: "Take Attendance" },
  { id: "secure", label: "Secure Attendance" },
  { id: "subjects", label: "Manage Subjects" },
  { id: "records", label: "Attendance Records" },
  { id: "institution", label: "Institution" },
  { id: "account", label: "Account" },
  { id: "success", label: "Success Hub" },
];

const studentNav = [
  { id: "subjects", label: "My Subjects" },
  { id: "progress", label: "My Progress & Support" },
  { id: "resources", label: "Academic Resources" },
  { id: "mentorship", label: "My Mentorship" },
  { id: "rewards", label: "My Rewards" },
  { id: "verify", label: "Verify attendance" },
  { id: "predict", label: "Predictive Intelligence" },
  { id: "communities", label: "Communities" },
  { id: "account", label: "Account status" },
];

export default function ClassroomApp() {
  const [health, setHealth] = useState(null);
  const [session, setSession] = useState(null);
  const [portal, setPortal] = useState(() => (joinCodeFromUrl() ? "student" : null));
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const boot = async () => {
    api.health().then(setHealth).catch(() => {});
    if (!hasSession()) return;
    try {
      setSession(await api.me());
    } catch {
      setSession(null);
      clearSession();
    }
  };

  useEffect(() => {
    boot();
  }, []);

  const signIn = (payload) => {
    saveSession(payload.token);
    setSession(payload.session);
    setPortal(null);
    setError("");
  };

  const logout = () => {
    clearSession();
    setSession(null);
    setPortal(null);
    setError("");
  };

  return (
    <div className={`classroom-root ${session ? "is-dash" : ""} ${session?.user_role === "student" ? "has-risk" : ""}`}>
      <main className="co-shell">
        {error && <Notice title="Something went wrong" body={error} tone="danger" />}
        {!session && !portal && <HomePortal setPortal={setPortal} />}
        {!session && portal === "teacher" && (
          <TeacherAuth health={health} busy={busy} setBusy={setBusy} setError={setError} signIn={signIn} onBack={() => { setError(""); setPortal(null); }} />
        )}
        {!session && portal === "staff" && (
          <StaffAuth health={health} busy={busy} setBusy={setBusy} setError={setError} signIn={signIn} onBack={() => { setError(""); setPortal(null); }} />
        )}
        {!session && portal === "student" && (
          <StudentAuth health={health} busy={busy} setBusy={setBusy} setError={setError} signIn={signIn} onBack={() => { setError(""); setPortal(null); }} />
        )}
        {!session && portal === "merchant" && (
          <MerchantAuth busy={busy} setBusy={setBusy} setError={setError} signIn={signIn} onBack={() => { setError(""); setPortal(null); }} />
        )}
        {session?.user_role === "teacher" && <TeacherDesk session={session} health={health} setError={setError} onLogout={logout} />}
        {session?.user_role === "student" && <StudentDesk session={session} setError={setError} onLogout={logout} />}
        {session?.user_role === "merchant" && <MerchantDesk session={session} onLogout={logout} />}
        {["counsellor", "administrator", "faculty", "mentor"].includes(session?.user_role) &&
          session?.user_role !== "teacher" &&
          session?.user_role !== "student" && <SuccessDesk session={session} setError={setError} onLogout={logout} />}
      </main>
    </div>
  );
}

function HomePortal({ setPortal }) {
  return (
    <div>
      <HomeHeader />
      <div className="co-portal-grid">
        {portals.map((item) => (
          <div key={item.id} className="co-portal">
            <p className="co-caption">{item.kicker}</p>
            <h2>{item.title}</h2>
            <p>{item.body}</p>
            <button
              type="button"
              className={`co-btn co-btn-stretch ${item.secondary ? "co-btn-secondary" : ""}`}
              onClick={() => setPortal(item.id)}
            >
              {item.cta}
            </button>
          </div>
        ))}
      </div>
      <HomeFooter />
    </div>
  );
}

function AuthCard({ kicker, title, caption, onBack, children }) {
  return (
    <div>
      <div className="co-auth-top">
        <DashHeader />
        <button type="button" className="co-btn co-btn-secondary" onClick={onBack}>
          Go back to Home
        </button>
      </div>
      <p className="co-caption text-center">{kicker}</p>
      <h1 className="co-auth-title">{title}</h1>
      {caption && <p className="mb-6 text-center text-sm text-[#64748B]">{caption}</p>}
      <div className="mx-auto max-w-xl">{children}</div>
      <DashFooter />
    </div>
  );
}

function TeacherAuth({ health, busy, setBusy, setError, signIn, onBack }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", name: "", registered_name: "", token: "", confirm_password: "" });
  const [notice, setNotice] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "login") signIn(await api.teacherLogin(form));
      else if (mode === "register") signIn(await api.teacherRegister(form));
      else if (mode === "forgot") {
        const res = await api.teacherForgot({ username: form.username, registered_name: form.registered_name, new_password: form.password, confirm_password: form.confirm_password });
        setNotice(res.detail);
        setMode("login");
      } else {
        const res = await api.teacherActivate({ username: form.username, token: form.token, password: form.password, confirm_password: form.confirm_password });
        setNotice(res.detail);
        setMode("login");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const titles = {
    login: { kicker: "Faculty access", title: "Login using password", caption: "The smarter way to connect classrooms." },
    register: { kicker: "Faculty onboarding", title: "Register your faculty profile", caption: "Create your Classora faculty workspace." },
    forgot: { kicker: "Password recovery", title: "Reset faculty password", caption: "Confirm the username and the name registered on the account." },
    activate: { kicker: "Account activation", title: "Activate faculty invitation", caption: "Use the one-time code from an invited faculty member. Codes expire after 7 days." },
  }[mode];
  return (
    <AuthCard kicker={titles.kicker} title={titles.title} caption={titles.caption} onBack={onBack}>
      {notice && <Notice title="Done" body={notice} tone="ok" />}
      <form onSubmit={submit}>
        {mode === "register" && <Field label="Enter name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />}
        {mode === "forgot" && <Field label="Registered name" value={form.registered_name} onChange={(e) => setForm({ ...form, registered_name: e.target.value })} />}
        {mode === "activate" && <Field label="Activation code" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} />}
        <Field label="Enter username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} placeholder="ananyaroy" />
        {mode !== "forgot" && mode !== "activate" && <Field label="Enter password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
        {(mode === "forgot" || mode === "activate") && (
          <>
            <Field label={mode === "forgot" ? "New password" : "Create password"} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Field label="Confirm password" type="password" value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })} />
          </>
        )}
        <hr className="co-hr" />
        <div className="grid gap-3 sm:grid-cols-2">
          <button disabled={busy} className="co-btn co-btn-stretch">
            {mode === "login" ? "Login" : mode === "register" ? "Register now" : mode === "forgot" ? "Reset password" : "Activate account"}
          </button>
          <button type="button" className="co-btn co-btn-stretch" onClick={() => setMode(mode === "register" ? "login" : "register")}>
            {mode === "register" ? "Login instead" : "Register instead"}
          </button>
        </div>
      </form>
      {mode === "login" && (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <button type="button" className="co-btn co-btn-stretch co-btn-secondary" onClick={() => setMode("forgot")}>Forgot password</button>
          <button type="button" className="co-btn co-btn-stretch co-btn-secondary" onClick={() => setMode("activate")}>Activate invitation</button>
        </div>
      )}
    </AuthCard>
  );
}

function StaffAuth({ health, busy, setBusy, setError, signIn, onBack }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ username: "", password: "", name: "", role: "counsellor", token: "", confirm_password: "" });
  const [notice, setNotice] = useState("");
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "login") signIn(await api.staffLogin(form));
      else if (mode === "register") signIn(await api.staffRegister(form));
      else {
        const res = await api.staffActivate({
          username: form.username,
          token: form.token,
          password: form.password,
          confirm_password: form.confirm_password,
        });
        setNotice(res.detail);
        setMode("login");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  const titles = {
    login: { kicker: "Staff access", title: "Login using password", caption: "Counsellor, administrator, faculty, and mentor workspaces." },
    register: { kicker: "Staff onboarding", title: "Register staff profile", caption: "Create a counsellor, administrator, faculty, or mentor account." },
    activate: { kicker: "Account activation", title: "Activate staff invitation", caption: "Use the one-time code from an administrator. Codes expire after 7 days." },
  }[mode];
  return (
    <AuthCard kicker={titles.kicker} title={titles.title} caption={titles.caption} onBack={onBack}>
      {notice && <Notice title="Done" body={notice} tone="ok" />}
      <form onSubmit={submit}>
        {mode === "register" && (
          <>
            <Field label="Enter name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            <label className="co-field">
              <span>Role</span>
              <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                <option value="counsellor">Counsellor</option>
                <option value="administrator">Administrator</option>
                <option value="faculty">Faculty</option>
                <option value="mentor">Mentor</option>
              </select>
            </label>
          </>
        )}
        {mode === "activate" && <Field label="Activation code" value={form.token} onChange={(e) => setForm({ ...form, token: e.target.value })} />}
        <Field label="Enter username" value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
        {mode !== "activate" && <Field label="Enter password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />}
        {mode === "activate" && (
          <>
            <Field label="Create password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
            <Field label="Confirm password" type="password" value={form.confirm_password} onChange={(e) => setForm({ ...form, confirm_password: e.target.value })} />
          </>
        )}
        <hr className="co-hr" />
        <div className="grid gap-3 sm:grid-cols-2">
          <button disabled={busy} className="co-btn co-btn-stretch">
            {mode === "login" ? "Login" : mode === "register" ? "Register now" : "Activate account"}
          </button>
          <button
            type="button"
            className="co-btn co-btn-stretch"
            onClick={() => setMode(mode === "register" ? "login" : mode === "activate" ? "login" : "register")}
          >
            {mode === "register" || mode === "activate" ? "Login instead" : "Register instead"}
          </button>
        </div>
      </form>
      {mode === "login" && (
        <div className="mt-3">
          <button type="button" className="co-btn co-btn-stretch co-btn-secondary" onClick={() => setMode("activate")}>Activate invitation</button>
        </div>
      )}
    </AuthCard>
  );
}

function StudentAuth({ health, busy, setBusy, setError, signIn, onBack }) {
  const [name, setName] = useState("");
  const [face, setFace] = useState(null);
  const [voice, setVoice] = useState(null);
  const [mode, setMode] = useState("login");
  const [info, setInfo] = useState("");

  const handleFace = async (file) => {
    setFace(file);
    setError("");
    if (!file) {
      setMode("login");
      setInfo("");
      return;
    }
    if (mode === "register") return;
    setBusy(true);
    try {
      const payload = await api.studentFace(file);
      if (!payload.matched) {
        setMode("register");
        setInfo(payload.detail || "Face detected. You're a new student — enter your name to register.");
        return;
      }
      signIn(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const register = async (event) => {
    event.preventDefault();
    if (!name) return setError("Enter your name to register.");
    if (!face) return setError("Capture your face with the camera first.");
    setBusy(true);
    setError("");
    try {
      const payload = await api.studentRegister({ name, face, voice });
      if (payload.voice_warning) setError(payload.voice_warning);
      signIn(payload);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthCard
      kicker="Student access"
      title={mode === "register" ? "New student — complete registration" : "Login using FaceID"}
      caption={
        mode === "register"
          ? "Your face is new to CLASSORA. Enter your name. Voice is optional, but needed later for classroom voice attendance."
          : "Allow the camera, look at the lens, then capture. If this face is already enrolled, you are signed in automatically."
      }
      onBack={onBack}
    >
      {health && !health.face_models_ready && (
        <Notice
          tone="warn"
          title="Face models are not loaded yet"
          body={`Camera login will fail until dlib + face_recognition_models finish installing. Missing: ${Object.entries(health.models || {}).filter(([, ok]) => !ok).map(([n]) => n).join(", ") || "unknown"}`}
        />
      )}
      {health && health.voice_models_ready && !health.voice_weights_loaded && (
        <Notice
          tone="warn"
          title="Voice model is warming up"
          body="First voice request loads Torch weights. Wait until this notice disappears, then record."
        />
      )}
      {info && <Notice title="Face detected" body={info} tone="ok" />}
      <form onSubmit={mode === "register" ? register : (event) => event.preventDefault()}>
        {mode === "register" && <Field label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="E.g. Hamza Rizvi" />}
        <div className="co-media mb-4">
          <CameraCapture onCapture={handleFace} captureLabel={busy && mode === "login" ? "Matching your face…" : "Capture face"} maxSide={720} />
        </div>
        {mode === "register" && (
          <div className="co-media mb-4">
            <MicRecorder onCapture={setVoice} label="Optional voice enrollment" hint='Record a short phrase like “I am present. My name is …”' />
          </div>
        )}
        {mode === "register" && (
          <button disabled={busy} className="co-btn co-btn-stretch">
            {busy ? "Saving your profile…" : "Create account"}
          </button>
        )}
        {mode === "login" && busy && <p className="text-center text-sm text-[#64748B]">Matching your face…</p>}
      </form>
    </AuthCard>
  );
}

function TeacherDesk({ session, health, setError, onLogout }) {
  const [tab, setTab] = useState("attendance");
  const [subjects, setSubjects] = useState([]);
  const [records, setRecords] = useState([]);
  const [form, setForm] = useState({ subject_code: "", name: "", section: "E" });
  const [subjectId, setSubjectId] = useState("");
  const [photos, setPhotos] = useState([]);
  const [audio, setAudio] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busyFace, setBusyFace] = useState(false);
  const [busyVoice, setBusyVoice] = useState(false);

  const reload = async () => {
    try {
      const rows = await api.teacherSubjects();
      setSubjects(rows);
      if (!subjectId && rows[0]) setSubjectId(String(rows[0].subject_id));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    reload();
  }, []);

  useEffect(() => {
    if (tab !== "records") return undefined;
    let live = true;
    api
      .teacherAttendance()
      .then((rows) => {
        if (live) setRecords(rows);
      })
      .catch((err) => {
        if (live) setError(err.message);
      });
    return () => {
      live = false;
    };
  }, [tab]);

  const names = (ids = []) => {
    const roster = preview?.roster || [];
    return ids
      .map((id) => roster.find((row) => Number(row.student_id) === Number(id))?.name || `#${id}`)
      .join(", ");
  };

  const runFace = async () => {
    if (!subjectId) return setError("Choose a subject first.");
    if (!photos.length) return setError("Capture at least one classroom photo.");
    setBusyFace(true);
    setError("");
    try {
      setPreview(await api.faceAttendance(subjectId, photos));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyFace(false);
    }
  };

  const runVoice = async () => {
    if (!subjectId) return setError("Choose a subject first.");
    if (!audio) return setError("Record classroom audio first.");
    setBusyVoice(true);
    setError("");
    try {
      setPreview(await api.voiceAttendance(subjectId, audio));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusyVoice(false);
    }
  };

  return (
    <div>
      <div className="co-auth-top mb-4">
        <DashHeader />
        <div className="max-w-md">
          <WelcomeBanner name={session.teacher_data?.name} />
          <button type="button" className="co-btn co-btn-secondary mt-3" onClick={onLogout}>Logout</button>
        </div>
      </div>
      <StretchNav items={teacherNav} value={tab} onChange={setTab} />
      <hr className="co-hr" />
      {tab === "subjects" && (
        <div>
          <p className="co-caption">Classroom</p>
          <h2 className="mb-4 text-[1.4rem] font-bold tracking-[-0.02em]">Manage Subjects</h2>
          <div className="grid gap-6 md:grid-cols-2">
            <form
              className="co-card"
              onSubmit={async (e) => {
                e.preventDefault();
                try {
                  await api.createSubject(form);
                  setForm({ subject_code: "", name: "", section: "E" });
                  reload();
                } catch (err) {
                  setError(err.message);
                }
              }}
            >
              <h3 className="mb-3 font-semibold">Create New Subject</h3>
              <Field label="Code" value={form.subject_code} onChange={(e) => setForm({ ...form, subject_code: e.target.value })} />
              <Field label="Name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
              <Field label="Section" value={form.section} onChange={(e) => setForm({ ...form, section: e.target.value })} />
              <button className="co-btn">Create</button>
            </form>
            <div className="space-y-3">
              {subjects.map((sub) => (
                <SubjectCard
                  key={sub.subject_id}
                  name={sub.name}
                  code={sub.subject_code}
                  section={sub.section}
                  stats={[["🫂", "Students", sub.total_students || 0], ["🕰️", "Classes", sub.total_classes || 0]]}
                >
                  <button
                    type="button"
                    className="co-btn co-btn-secondary mt-3"
                    onClick={async () => {
                      try {
                        const share = await api.shareSubject(sub.subject_code);
                        await navigator.clipboard.writeText(`${window.location.origin}${share.join_url}`);
                        window.alert(`${share.message}\nCopied join link: ${window.location.origin}${share.join_url}`);
                      } catch (err) {
                        setError(err.message);
                      }
                    }}
                  >
                    Share Code: {sub.name}
                  </button>
                </SubjectCard>
              ))}
              {!subjects.length && <EmptyState title="No subjects found." body="Create a subject above to start building your connected classroom." />}
            </div>
          </div>
        </div>
      )}
      {tab === "secure" && <SecureAttendance session={session} />}
      {tab === "attendance" && (
        <div className="co-card space-y-6">
          <p className="co-caption">Classora intelligence</p>
          <h2 className="text-[1.4rem] font-bold tracking-[-0.02em]">Take AI Attendance</h2>
          <p className="text-sm text-[#64748B]">Capture classroom photos or use voice — Classora recognizes enrolled students.</p>
          <label className="co-field">
            <span>Select Subject</span>
            <select value={subjectId} onChange={(e) => setSubjectId(e.target.value)}>
            {subjects.map((sub) => (
              <option key={sub.subject_id} value={sub.subject_id}>
                {sub.subject_code} — {sub.name}
              </option>
            ))}
          </select>
          </label>
          <div className="grid gap-6 lg:grid-cols-2">
            <div className="rounded-3xl border border-[#E2E8F0] p-4">
              <h2 className="font-semibold">Face attendance</h2>
              {health && !health.face_models_ready && (
                <p className="mt-2 text-sm text-amber-700">Face models are not ready yet.</p>
              )}
              <div className="mt-3">
                <CameraCapture
                  gallery
                  mirrorPreview={false}
                  maxSide={960}
                  captureLabel="Add classroom photo"
                  label="Point the camera at the class"
                  hint="Capture several photos if students are spread out, then run analysis."
                  onFiles={setPhotos}
                />
              </div>
              <button type="button" disabled={busyFace} onClick={runFace} className="co-btn mt-4">
                {busyFace ? "AI is scanning…" : "Run Face Analysis"}
              </button>
            </div>
            <div className="rounded-3xl border border-[#E2E8F0] p-4">
              <h2 className="font-semibold">Voice attendance</h2>
              {health && health.voice_models_ready && !health.voice_weights_loaded && (
                <p className="mt-2 text-sm text-amber-700">Voice model is still loading. Wait a few seconds, then try again.</p>
              )}
              <div className="mt-3">
                <MicRecorder
                  onCapture={setAudio}
                  label="Record students saying “I am present”"
                  hint="Walk the mic around the room. Stop when everyone has spoken."
                />
              </div>
              <button type="button" disabled={busyVoice} onClick={runVoice} className="co-btn co-btn-secondary mt-4">
                {busyVoice ? "Processing audio…" : "Use Voice Attendance"}
              </button>
            </div>
          </div>
          {preview && (
            <div className="rounded-2xl bg-[#F8FAFC] p-4">
              <p className="text-sm text-[#334155]">
                <strong>Present:</strong> {names(preview.present_ids) || "none"}
              </p>
              <p className="mt-1 text-sm text-[#334155]">
                <strong>Absent:</strong> {names(preview.absent_ids) || "none"}
              </p>
              {Number(preview.unknown_faces) > 0 && (
                <p className="mt-2 text-sm text-amber-800">
                  {preview.unknown_faces} face{Number(preview.unknown_faces) === 1 ? "" : "s"} in the photo {Number(preview.unknown_faces) === 1 ? "is" : "are"} not on this subject’s roster.
                  Enroll that student with the subject join code, then run analysis again. Attendance only marks enrolled names present or absent.
                </p>
              )}
              {!(preview.present_ids || []).length && !Number(preview.unknown_faces) && (
                <p className="mt-2 text-sm text-amber-800">
                  No enrolled face matched. Confirm the student registered FaceID and is enrolled in this subject.
                </p>
              )}
              <button
                type="button"
                className="co-btn mt-3"
                onClick={async () => {
                  try {
                    await api.confirmAttendance({ subject_id: Number(subjectId), present_ids: preview.present_ids, absent_ids: preview.absent_ids });
                    setPreview(null);
                    reload();
                  } catch (err) {
                    setError(err.message);
                  }
                }}
              >
                Save attendance session
              </button>
            </div>
          )}
        </div>
      )}
      {tab === "records" && (
        <div>
          <p className="co-caption">Records</p>
          <h2 className="mb-2 text-[1.4rem] font-bold">Attendance Records</h2>
          <p className="mb-4 text-sm text-[#64748B]">Review past attendance sessions for your subjects.</p>
          <GroupedRecords records={records} />
        </div>
      )}
      {tab === "institution" && <InstitutionPanel setError={setError} session={session} />}
      {tab === "account" && <AccountPanel session={session} setError={setError} />}
      {tab === "success" && <SuccessWorkspace session={session} setError={setError} />}
      <DashFooter />
    </div>
  );
}

function StudentDesk({ session, setError, onLogout }) {
  const [tab, setTab] = useState(studentTabFromUrl);
  const [data, setData] = useState({ subjects: [], attendance: [] });
  const [code, setCode] = useState(() => joinCodeFromUrl());
  const [joined, setJoined] = useState("");
  const [risk, setRisk] = useState(null);
  const [workspace, setWorkspace] = useState(null);
  const [resourceNonce, setResourceNonce] = useState(0);
  const shell = useMemo(() => studentWorkspaceShell(session, risk), [session, risk]);

  const reload = async () => {
    try {
      setData(await api.studentSubjects());
      setRisk(await api.studentRisk());
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    reload();
    let live = true;
    api
      .workspace()
      .then((ws) => {
        if (live) setWorkspace(ws);
      })
      .catch((err) => {
        if (live) setError(err.message);
      });
    return () => {
      live = false;
    };
  }, []);

  useEffect(() => {
    const pending = joinCodeFromUrl();
    if (!pending) return;
    (async () => {
      try {
        await api.enroll(pending);
        setJoined(`Enrolled in ${pending}`);
        setCode("");
        const url = new URL(window.location.href);
        url.searchParams.delete("join-code");
        window.history.replaceState({}, "", url.pathname + url.search);
        reload();
      } catch (err) {
        setError(err.message);
      }
    })();
  }, []);

  const stats = useMemo(() => {
    const map = {};
    for (const log of data.attendance || []) {
      const sid = log.subject_id;
      map[sid] ||= { total: 0, attended: 0 };
      map[sid].total += 1;
      if (log.is_present) map[sid].attended += 1;
    }
    return map;
  }, [data]);

  return (
    <div>
      <div className="co-auth-top mb-4">
        <DashHeader />
        <div className="max-w-md">
          <WelcomeBanner name={session.student_data?.name} />
          <button type="button" className="co-btn co-btn-secondary mt-3" onClick={onLogout}>Logout</button>
        </div>
      </div>
      {joined && <Notice tone="ok" title="Enrolled" body={joined} />}
      <StretchNav
        items={studentNav}
        value={tab}
        onChange={(next) => {
          setTab(next);
          const url = new URL(window.location.href);
          if (next === "subjects") url.searchParams.delete("tab");
          else url.searchParams.set("tab", next);
          ["year", "semester", "subject", "type", "source", "search", "sort", "page"].forEach((key) => url.searchParams.delete(key));
          window.history.replaceState({}, "", url.pathname + url.search);
          if (next === "resources") setResourceNonce((value) => value + 1);
        }}
        className="co-student-nav"
      />
      <hr className="co-hr" />
      {tab === "subjects" && (
        <div>
          <p className="co-caption">Classroom</p>
          <h2 className="mb-4 text-[1.4rem] font-bold">My Subjects</h2>
          <form
            className="mb-6 flex gap-3"
            onSubmit={async (e) => {
              e.preventDefault();
              try {
                await api.enroll(code);
                setCode("");
                reload();
              } catch (err) {
                setError(err.message);
              }
            }}
          >
            <input className="co-input flex-1" placeholder="Subject code e.g. CS1317" value={code} onChange={(e) => setCode(e.target.value)} />
            <button className="co-btn">Enroll</button>
          </form>
          <div className="grid gap-4 md:grid-cols-2">
            {(data.subjects || []).map((node) => {
              const sub = node.subjects || node;
              const st = stats[sub.subject_id] || { total: 0, attended: 0 };
              return (
                <SubjectCard
                  key={sub.subject_id}
                  name={sub.name}
                  code={sub.subject_code}
                  section={sub.section}
                  stats={[["✅", "Attended", `${st.attended}/${st.total}`]]}
                >
                  <button
                    type="button"
                    className="co-btn co-btn-tertiary mt-3"
                    onClick={async () => {
                      await api.unenroll(sub.subject_id);
                      reload();
                    }}
                  >
                    Unenroll
                  </button>
                </SubjectCard>
              );
            })}
            {!(data.subjects || []).length && <EmptyState title="No subjects yet." body="Ask your faculty member for a share code, or enroll above." />}
          </div>
        </div>
      )}
      {tab === "resources" && <AcademicResources key={resourceNonce} session={session} />}
      {tab === "verify" && <SecureAttendance session={session} />}
      {tab === "communities" && <Communities session={session} />}
      {tab !== "subjects" && tab !== "resources" && tab !== "verify" && tab !== "communities" && (
        <SuccessWorkspace
          session={session}
          setError={setError}
          defaultModule={tab === "mentorship" ? "Anonymous Mentorship" : tab === "account" ? "Account" : tab === "rewards" ? "My Rewards" : tab === "verify" ? "Verify Attendance" : tab === "predict" ? "Predictive Intelligence" : tab === "communities" ? "Communities" : "My Digital Twin"}
          cached={workspace || shell}
          onCached={setWorkspace}
        />
      )}
      <RiskWidget
        payload={risk?.risk}
        onGoto={(kind) => {
          setTab("progress");
          window.dispatchEvent(new CustomEvent("classora-risk-goto", { detail: kind }));
        }}
      />
      <DashFooter />
    </div>
  );
}

function MerchantAuth({ busy, setBusy, setError, signIn, onBack }) {
  const [form, setForm] = useState({ merchantId: "", accessCode: "" });
  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      signIn(await api.merchantLogin({ merchantId: form.merchantId, accessCode: form.accessCode }));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <AuthCard kicker="CAMPUS MERCHANT" title="Redeem CLASSORA Rewards" caption="Use the access code issued by your institution administrator." onBack={onBack}>
      <form className="space-y-3" onSubmit={submit}>
        <Field label="Merchant ID"><input className="co-input" value={form.merchantId} onChange={(e) => setForm({ ...form, merchantId: e.target.value })} /></Field>
        <Field label="Access code"><input className="co-input" type="password" value={form.accessCode} onChange={(e) => setForm({ ...form, accessCode: e.target.value })} /></Field>
        <button className="co-btn co-btn-stretch" disabled={busy}>{busy ? "Signing in…" : "Enter merchant desk"}</button>
      </form>
    </AuthCard>
  );
}

function MerchantDesk({ session, onLogout }) {
  return (
    <div>
      <div className="co-auth-top mb-4">
        <DashHeader />
        <div className="max-w-md">
          <WelcomeBanner name={session.merchant_data?.name || "Merchant"} subtitle="Validate vouchers. No academic or counselling data." />
          <button type="button" className="co-btn co-btn-secondary mt-3" onClick={onLogout}>Logout</button>
        </div>
      </div>
      <hr className="co-hr" />
      <ClassoraRewards session={session} />
      <DashFooter />
    </div>
  );
}

function SuccessDesk({ session, setError, onLogout }) {
  return (
    <div>
      <div className="co-auth-top mb-4">
        <DashHeader />
        <div className="max-w-md">
          <WelcomeBanner name={session.staff_data?.name || session.user_role} subtitle="Student Success Hub" />
          <button type="button" className="co-btn co-btn-secondary mt-3" onClick={onLogout}>Logout</button>
        </div>
      </div>
      <hr className="co-hr" />
      <SuccessWorkspace session={session} setError={setError} />
      <DashFooter />
    </div>
  );
}

function GroupedRecords({ records }) {
  const rows = useMemo(() => {
    const map = {};
    for (const row of records || []) {
      const raw = row.timestamp || "";
      const subject = row.subjects?.name || row.subject_id;
      const code = row.subjects?.subject_code || "";
      const key = `${raw}|${subject}|${code}`;
      map[key] ||= { Time: formatDateTime(raw) || String(raw).split(".")[0], Subject: subject, "Subject Code": code, present: 0, total: 0 };
      map[key].total += 1;
      if (row.is_present) map[key].present += 1;
    }
    return Object.values(map).map((row) => ({
      Time: row.Time,
      Subject: row.Subject,
      "Subject Code": row["Subject Code"],
      Stats: `${row.present} / ${row.total} students`,
    }));
  }, [records]);
  if (!rows.length) return <p className="text-sm text-[#64748B]">No attendance records yet. Records appear after you save a session.</p>;
  return (
    <div className="co-table-wrap">
      <table className="co-table">
        <thead className="bg-[#F8FAFC] text-[#64748B]">
          <tr>{["Time", "Subject", "Subject Code", "Stats"].map((k) => <th key={k} className="px-4 py-3">{k}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-t border-[#E2E8F0]">
              <td className="px-4 py-3">{row.Time}</td>
              <td className="px-4 py-3">{row.Subject}</td>
              <td className="px-4 py-3">{row["Subject Code"]}</td>
              <td className="px-4 py-3">{row.Stats}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
