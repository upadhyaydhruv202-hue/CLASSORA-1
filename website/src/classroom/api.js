const TOKEN_KEY = "classora_token";
const API_BASE = String(import.meta.env.VITE_API_URL || "").replace(/\/$/, "");

async function request(path, { method = "GET", body, form, auth = true, timeoutMs = 25000 } = {}) {
  const headers = {};
  if (auth) {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) headers.Authorization = `Bearer ${token}`;
  }
  let payload = body;
  if (form) {
    payload = form;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const controller = timeoutMs ? new AbortController() : null;
  const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, signal: controller?.signal });
  } catch (err) {
    if (err?.name === "AbortError") {
      throw new Error("That request took too long. The voice model may still be starting — wait 15 seconds and try once more.");
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || data.message || `Request failed (${res.status})`);
  }
  return data;
}

let workspacePromise = null;

function loadWorkspace(force = false) {
  if (force || !workspacePromise) {
    workspacePromise = request("/api/success/workspace").catch((err) => {
      workspacePromise = null;
      throw err;
    });
  }
  return workspacePromise;
}

export const api = {
  health: () => request("/api/health", { auth: false }),
  me: () => request("/api/me"),
  teacherLogin: (body) => request("/api/auth/teacher/login", { method: "POST", body, auth: false, timeoutMs: 8000 }),
  teacherRegister: (body) => request("/api/auth/teacher/register", { method: "POST", body, auth: false }),
  staffLogin: (body) => request("/api/auth/staff/login", { method: "POST", body, auth: false }),
  staffRegister: (body) => request("/api/auth/staff/register", { method: "POST", body, auth: false }),
  studentFace: (file) => {
    const form = new FormData();
    form.append("face", file);
    return request("/api/auth/student/face", { method: "POST", form, auth: false });
  },
  studentRegister: ({ name, face, voice }) => {
    const form = new FormData();
    form.append("name", name);
    if (face) form.append("face", face);
    if (voice) form.append("voice", voice);
    return request("/api/auth/student/register", { method: "POST", form, auth: false });
  },
  studentQuick: (student_id) =>
    request(`/api/auth/student/quick?student_id=${student_id}`, { method: "POST", auth: false }),
  teacherSubjects: () => request("/api/teacher/subjects"),
  createSubject: (body) => request("/api/teacher/subjects", { method: "POST", body }),
  teacherAttendance: () => request("/api/teacher/attendance"),
  institution: () => request("/api/teacher/institution"),
  faceAttendance: (subjectId, files) => {
    const form = new FormData();
    form.append("subject_id", subjectId);
    [...files].forEach((file) => form.append("photos", file));
    return request("/api/teacher/attendance/face", { method: "POST", form });
  },
  voiceAttendance: (subjectId, file) => {
    const form = new FormData();
    form.append("subject_id", subjectId);
    form.append("audio", file);
    return request("/api/teacher/attendance/voice", { method: "POST", form, timeoutMs: 20000 });
  },
  confirmAttendance: (body) => request("/api/teacher/attendance/confirm", { method: "POST", body }),
  studentDirectory: () => request("/api/student/directory", { auth: false }),
  studentSubjects: () => request("/api/student/subjects"),
  enroll: (subject_code) => request("/api/student/enroll", { method: "POST", body: { subject_code } }),
  unenroll: (id) => request(`/api/student/subjects/${id}`, { method: "DELETE" }),
  studentRisk: () => request("/api/student/risk"),
  successHub: () => request("/api/success/hub"),
  successStudent: (id) => request(`/api/success/student/${id}`),
  teacherForgot: (body) => request("/api/auth/teacher/forgot", { method: "POST", body, auth: false }),
  teacherActivate: (body) => request("/api/auth/teacher/activate", { method: "POST", body, auth: false }),
  changePassword: (body) => request("/api/teacher/password", { method: "POST", body }),
  inviteTeacher: (body) => request("/api/teacher/invites", { method: "POST", body }),
  teacherInvites: () => request("/api/teacher/invites"),
  loginHistory: () => request("/api/teacher/login-history"),
  shareSubject: (code) => request(`/api/teacher/share/${encodeURIComponent(code)}`),
  workspace: (force = false) => loadWorkspace(force),
  sendHelp: (body) => request("/api/success/help", { method: "POST", body }),
  bookAppointment: (body) => request("/api/success/appointment", { method: "POST", body }),
  submitRecommend: (body) => request("/api/success/recommend", { method: "POST", body }),
  createCase: (body) => request("/api/success/case", { method: "POST", body }),
  recordOutcome: (body) => request("/api/success/outcome", { method: "POST", body }),
  askAssistant: (body) => request("/api/success/assistant", { method: "POST", body }),
  staffInvite: (body) => request("/api/staff/invite", { method: "POST", body }),
  mentorshipList: () => request("/api/mentorship"),
  mentorshipAssign: (body) => request("/api/mentorship/assign", { method: "POST", body }),
  mentorshipOne: (id) => request(`/api/mentorship/${id}`),
  mentorshipMessages: (id) => request(`/api/mentorship/${id}/messages`),
  mentorshipMessage: (id, body) => request(`/api/mentorship/${id}/messages`, { method: "POST", body }),
  mentorshipSession: (id, body) => request(`/api/mentorship/${id}/sessions`, { method: "POST", body }),
  mentorshipFeedback: (id, body) => request(`/api/mentorship/${id}/feedback`, { method: "POST", body }),
  mentorshipReassign: (id) => request(`/api/mentorship/${id}/reassign`, { method: "POST" }),
  mentorshipSuspend: (id) => request(`/api/mentorship/${id}/suspend`, { method: "POST" }),
  createComplaint: (body) => request("/api/moderation/complaints", { method: "POST", body }),
  submitAppeal: (body) => request("/api/moderation/appeals", { method: "POST", body }),
  openComplaint: (id) => request(`/api/moderation/complaints/${id}/open`, { method: "POST" }),
  decideComplaint: (id, body) => request(`/api/moderation/complaints/${id}/decide`, { method: "POST", body }),
};

export function saveSession(token) {
  localStorage.setItem(TOKEN_KEY, token);
  workspacePromise = null;
}

export function clearSession() {
  localStorage.removeItem(TOKEN_KEY);
  workspacePromise = null;
}

export function hasSession() {
  return Boolean(localStorage.getItem(TOKEN_KEY));
}
