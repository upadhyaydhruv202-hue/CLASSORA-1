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
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, signal: controller?.signal, cache: "no-store" });
  } catch (err) {
    if (err?.name === "AbortError") {
      if (String(path).includes("voice") || String(path).includes("/register")) {
        throw new Error("Voice processing took too long. The voice model loads on first use — wait a few seconds and try once more.");
      }
      throw new Error("That request took too long. Confirm the API is running on port 8000, then try again.");
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
    workspacePromise = request("/api/success/workspace", { timeoutMs: 120000 }).catch((err) => {
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
    return request("/api/auth/student/face", { method: "POST", form, auth: false, timeoutMs: 45000 });
  },
  studentRegister: ({ name, face, voice }) => {
    const form = new FormData();
    form.append("name", name);
    if (face) form.append("face", face);
    if (voice) form.append("voice", voice);
    return request("/api/auth/student/register", { method: "POST", form, auth: false, timeoutMs: 120000 });
  },
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
    return request("/api/teacher/attendance/voice", { method: "POST", form, timeoutMs: 120000 });
  },
  confirmAttendance: (body) => request("/api/teacher/attendance/confirm", { method: "POST", body }),
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
  ackHelp: (body) => request("/api/success/help/ack", { method: "POST", body }),
  bookAppointment: (body) => request("/api/success/appointment", { method: "POST", body }),
  connectAppointment: (body) => request("/api/success/appointment/connect", { method: "POST", body }),
  submitRecommend: (body) => request("/api/success/recommend", { method: "POST", body }),
  createCase: (body) => request("/api/success/case", { method: "POST", body }),
  recordOutcome: (body) => request("/api/success/outcome", { method: "POST", body }),
  askAssistant: (body) => request("/api/success/assistant", { method: "POST", body }),
  staffInvite: (body) => request("/api/staff/invite", { method: "POST", body }),
  staffActivate: (body) => request("/api/auth/staff/activate", { method: "POST", body, auth: false }),
  staffInvites: () => request("/api/staff/invites"),
  successSearch: (q) => request(`/api/success/search?q=${encodeURIComponent(q || "")}`),
  successReport: () => request("/api/success/report"),
  successSettings: () => request("/api/success/settings", { timeoutMs: 20000 }),
  saveSettings: async (body) => {
    const res = await request("/api/success/settings", { method: "POST", body });
    workspacePromise = null;
    return res;
  },
  successImport: (file, kind = "academic") => {
    const form = new FormData();
    form.append("kind", kind);
    form.append("file", file);
    return request("/api/success/import", { method: "POST", form, timeoutMs: 60000 });
  },
  createTask: (body) => request("/api/success/task", { method: "POST", body }),
  completeTask: (body) => request("/api/success/task/done", { method: "POST", body }),
  resolveAlert: (body) => request("/api/success/alert/resolve", { method: "POST", body }),
  mentorshipList: () => request("/api/mentorship"),
  mentorshipAssign: (body) => request("/api/mentorship/assign", { method: "POST", body }),
  mentorshipOne: (id) => request(`/api/mentorship/${id}`),
  mentorshipMessages: (id) => request(`/api/mentorship/${id}/messages`),
  mentorshipMessage: (id, body) => request(`/api/mentorship/${id}/messages`, { method: "POST", body }),
  mentorshipSession: (id, body) => request(`/api/mentorship/${id}/sessions`, { method: "POST", body }),
  mentorshipFeedback: (id, body) => request(`/api/mentorship/${id}/feedback`, { method: "POST", body }),
  mentorshipReassign: (id) => request(`/api/mentorship/${id}/reassign`, { method: "POST" }),
  mentorshipClose: (id) => request(`/api/mentorship/${id}/close`, { method: "POST" }),
  mentorshipSuspend: (id) => request(`/api/mentorship/${id}/suspend`, { method: "POST" }),
  createComplaint: (body) => request("/api/moderation/complaints", { method: "POST", body }),
  submitAppeal: (body) => request("/api/moderation/appeals", { method: "POST", body }),
  reviewAppeal: (body) => request("/api/moderation/appeals/review", { method: "POST", body }),
  openComplaint: (id) => request(`/api/moderation/complaints/${id}/open`, { method: "POST" }),
  decideComplaint: (id, body) => request(`/api/moderation/complaints/${id}/decide`, { method: "POST", body }),
  syncAcademicResources: (body = {}) => request("/api/academic-resources/sync", { method: "POST", body, timeoutMs: 180000 }),
  academicCatalog: (params = {}) => request(`/api/academic-resources/catalog${academicQuery(params)}`),
  academicResources: (params = {}) => request(`/api/academic-resources${academicQuery(params)}`),
  academicResource: (id) => request(`/api/academic-resources/${id}`),
  createAcademicResource: (body) => request("/api/academic-resources", { method: "POST", body }),
  updateAcademicResource: (id, body) => request(`/api/academic-resources/${id}`, { method: "PUT", body }),
  deactivateAcademicResource: (id) => request(`/api/academic-resources/${id}`, { method: "DELETE" }),
  verifyAcademicResource: (id) => request(`/api/academic-resources/${id}/verify`, { method: "POST" }),
  reportAcademicResource: (id, body) => request(`/api/academic-resources/${id}/report`, { method: "POST", body }),
  createAcademicSubject: (body) => request("/api/academic-subjects", { method: "POST", body }),
  updateAcademicSubject: (id, body) => request(`/api/academic-subjects/${id}`, { method: "PUT", body }),
  createAcademicSource: (body) => request("/api/academic-sources", { method: "POST", body }),
  updateAcademicSource: (id, body) => request(`/api/academic-sources/${id}`, { method: "PUT", body }),
  createAcademicType: (body) => request("/api/academic-resource-types", { method: "POST", body }),
  academicReports: (status = "") => request(`/api/academic-resource-reports${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  reviewAcademicReport: (id, body) => request(`/api/academic-resource-reports/${id}/review`, { method: "POST", body }),
  anomalies: (params = {}) => request(`/api/institutional-anomalies${academicQuery(params)}`),
  anomalySummary: () => request("/api/institutional-anomalies/summary"),
  anomalySettings: () => request("/api/institutional-anomalies/settings"),
  saveAnomalySettings: (body) => request("/api/institutional-anomalies/settings", { method: "PUT", body }),
  analyzeAnomalies: () => request("/api/institutional-anomalies/analyze", { method: "POST", timeoutMs: 180000 }),
  anomaly: (id) => request(`/api/institutional-anomalies/${id}`),
  anomalyTimeline: (id) => request(`/api/institutional-anomalies/${id}/timeline`),
  anomalyEvidence: (id) => request(`/api/institutional-anomalies/${id}/evidence`),
  anomalyCohort: (id) => request(`/api/institutional-anomalies/${id}/cohort`),
  anomalyNotes: (id) => request(`/api/institutional-anomalies/${id}/notes`),
  addAnomalyNote: (id, body) => request(`/api/institutional-anomalies/${id}/notes`, { method: "POST", body }),
  acknowledgeAnomaly: (id) => request(`/api/institutional-anomalies/${id}/acknowledge`, { method: "POST" }),
  investigateAnomaly: (id) => request(`/api/institutional-anomalies/${id}/investigate`, { method: "POST" }),
  resolveAnomaly: (id) => request(`/api/institutional-anomalies/${id}/resolve`, { method: "POST" }),
  dismissAnomaly: (id) => request(`/api/institutional-anomalies/${id}/dismiss`, { method: "POST" }),
  dropoutOverview: () => request("/api/institutional-dropout/overview"),
  dropoutSummary: () => request("/api/institutional-dropout/summary"),
  dropoutSettings: () => request("/api/institutional-dropout/settings"),
  saveDropoutSettings: (body) => request("/api/institutional-dropout/settings", { method: "PUT", body }),
  analyzeDropout: () => request("/api/institutional-dropout/analyze", { method: "POST", timeoutMs: 180000 }),
  dropoutTrends: () => request("/api/institutional-dropout/trends"),
  dropoutFactors: (params = {}) => request(`/api/institutional-dropout/factors${academicQuery(params)}`),
  dropoutFactor: (id) => request(`/api/institutional-dropout/factors/${encodeURIComponent(id)}`),
  dropoutDepartments: () => request("/api/institutional-dropout/departments"),
  dropoutDepartment: (id) => request(`/api/institutional-dropout/departments/${encodeURIComponent(id)}`),
  dropoutSemesters: () => request("/api/institutional-dropout/semesters"),
  dropoutCourses: () => request("/api/institutional-dropout/courses"),
  dropoutHeatmap: () => request("/api/institutional-dropout/heatmap"),
  dropoutIntersections: () => request("/api/institutional-dropout/intersections"),
  dropoutRecommendations: () => request("/api/institutional-dropout/recommendations"),
  dropoutCompare: (params = {}) => request(`/api/institutional-dropout/compare${academicQuery(params)}`),
  dropoutReport: () => request("/api/institutional-dropout/report"),
  dropoutFirstYear: () => request("/api/institutional-dropout/first-year"),
  dropoutOutcomes: () => request("/api/institutional-dropout/outcomes"),
  recordDropoutOutcome: (body) => request("/api/institutional-dropout/outcomes", { method: "POST", body }),
  importDropoutOutcomes: (body) => request("/api/institutional-dropout/outcomes/import", { method: "POST", body }),
  rewardWallet: (studentId) => request(`/api/rewards/wallet${studentId != null ? `?student_id=${encodeURIComponent(studentId)}` : ""}`),
  rewardTransactions: (params = {}) => request(`/api/rewards/transactions${academicQuery(params)}`),
  rewardAchievements: (params = {}) => request(`/api/rewards/achievements${academicQuery(params)}`),
  submitRewardAchievement: (body) => request("/api/rewards/achievements", { method: "POST", body }),
  awardReward: (body) => request("/api/rewards/awards", { method: "POST", body }),
  verifyReward: (id, body) => request(`/api/rewards/achievements/${id}/verify`, { method: "POST", body }),
  approveReward: (id, body = {}) => request(`/api/rewards/requests/${id}/approve`, { method: "POST", body }),
  rejectReward: (id, body) => request(`/api/rewards/requests/${id}/reject`, { method: "POST", body }),
  rewardRequests: () => request("/api/rewards/requests"),
  reverseReward: (id, body) => request(`/api/rewards/transactions/${id}/reverse`, { method: "POST", body }),
  adjustReward: (body) => request("/api/rewards/adjustments", { method: "POST", body }),
  recommendReward: (params = {}) => request(`/api/rewards/recommend${academicQuery(params)}`),
  rewardRules: () => request("/api/rewards/rules"),
  rewardSettings: () => request("/api/rewards/settings"),
  saveRewardSettings: (body) => request("/api/rewards/settings", { method: "PUT", body }),
  rewardPolicies: () => request("/api/rewards/policies"),
  saveRewardPolicy: (body) => request("/api/rewards/policies", { method: "POST", body }),
  rewardMarketplace: (params = {}) => request(`/api/rewards/marketplace${academicQuery(params)}`),
  claimRewardOffer: (id, body = {}) => request(`/api/rewards/offers/${id}/claim`, { method: "POST", body }),
  rewardVouchers: (status = "") => request(`/api/rewards/vouchers${status ? `?status=${encodeURIComponent(status)}` : ""}`),
  rewardVoucher: (id) => request(`/api/rewards/vouchers/${id}`),
  cancelRewardVoucher: (id, body) => request(`/api/rewards/vouchers/${id}/cancel`, { method: "POST", body }),
  validateRedemption: (body) => request("/api/rewards/redemptions/validate", { method: "POST", body }),
  confirmRedemption: (body) => request("/api/rewards/redemptions/confirm", { method: "POST", body }),
  rewardMerchants: () => request("/api/rewards/merchants"),
  saveRewardMerchant: (body) => request("/api/rewards/merchants", { method: "POST", body }),
  saveRewardOffer: (body) => request("/api/rewards/offers", { method: "POST", body }),
  rewardAnalytics: () => request("/api/rewards/analytics"),
  rewardLeaderboard: () => request("/api/rewards/leaderboard"),
  merchantLogin: (body) => request("/api/rewards/merchant/login", { method: "POST", body, auth: false }),
  createAttendanceSession: (body) => request("/api/attendance/sessions", { method: "POST", body }),
  attendanceSessions: () => request("/api/attendance/sessions"),
  attendanceSession: (id) => request(`/api/attendance/sessions/${encodeURIComponent(id)}`),
  analyzeAttendanceSession: (id, files) => {
    const form = new FormData();
    [...files].forEach((file) => form.append("photos", file));
    return request(`/api/attendance/sessions/${encodeURIComponent(id)}/analyze`, { method: "POST", form, timeoutMs: 120000 });
  },
  completeAttendanceSession: (id, body = {}) => request(`/api/attendance/sessions/${encodeURIComponent(id)}/complete`, { method: "POST", body }),
  cancelAttendanceSession: (id, body) => request(`/api/attendance/sessions/${encodeURIComponent(id)}/cancel`, { method: "POST", body }),
  finalizeMatchedAttendance: (id, body) => request(`/api/attendance/sessions/${encodeURIComponent(id)}/finalize-matched`, { method: "POST", body }),
  correctAttendance: (id, body) => request(`/api/attendance/sessions/${encodeURIComponent(id)}/correction`, { method: "POST", body }),
  attendancePending: () => request("/api/attendance/student/pending"),
  attendanceHistory: () => request("/api/attendance/student/history"),
  issueAttendanceQr: (body) => request("/api/attendance/verification/qr", { method: "POST", body }),
  issueAttendanceCode: (body) => request("/api/attendance/verification/code", { method: "POST", body }),
  confirmAttendanceVerification: (body) => request("/api/attendance/verification/confirm", { method: "POST", body }),
  registerAttendanceDevice: (body = {}) => request("/api/attendance/device/register", { method: "POST", body }),
  attendanceDispute: (id, body) => request(`/api/attendance/sessions/${encodeURIComponent(id)}/dispute`, { method: "POST", body }),
  attendanceSettings: () => request("/api/attendance/settings"),
  saveAttendanceSettings: (body) => request("/api/attendance/settings", { method: "PUT", body }),
  attendanceAnalytics: () => request("/api/attendance/analytics"),
  predictionOverview: () => request("/api/predictions/overview"),
  predictionDocuments: () => request("/api/predictions/documents"),
  predictionDocument: (id) => request(`/api/predictions/documents/${encodeURIComponent(id)}`),
  addPredictionText: (body) => request("/api/predictions/documents", { method: "POST", body, timeoutMs: 60000 }),
  uploadPredictionFile: (file, extra = {}) => {
    const form = new FormData();
    form.append("file", file);
    if (extra.title) form.append("title", extra.title);
    if (extra.documentType) form.append("documentType", extra.documentType);
    if (extra.subject) form.append("subject", extra.subject);
    if (extra.official != null) form.append("official", extra.official ? "true" : "false");
    return request("/api/predictions/documents/upload", { method: "POST", form, timeoutMs: 90000 });
  },
  patchPredictionDocument: (id, body) => request(`/api/predictions/documents/${encodeURIComponent(id)}`, { method: "PATCH", body }),
  deletePredictionDocument: (id) => request(`/api/predictions/documents/${encodeURIComponent(id)}`, { method: "DELETE" }),
  reprocessPredictionDocument: (id) => request(`/api/predictions/documents/${encodeURIComponent(id)}/reprocess`, { method: "POST", timeoutMs: 60000 }),
  analyzePredictions: (body = {}) => request("/api/predictions/analyze", { method: "POST", body, timeoutMs: 60000 }),
  predictionAcademic: (params = {}) => request(`/api/predictions/academic${academicQuery(params)}`),
  predictionExamDate: (params = {}) => request(`/api/predictions/exam-date${academicQuery(params)}`),
  predictionQuestions: (params = {}) => request(`/api/predictions/questions${academicQuery(params)}`),
  predictionTopics: (params = {}) => request(`/api/predictions/topics${academicQuery(params)}`),
  predictionCareer: (params = {}) => request(`/api/predictions/career${academicQuery(params)}`),
  predictionQuery: (body) => request("/api/predictions/query", { method: "POST", body, timeoutMs: 60000 }),
  predictionHistory: (limit = 30) => request(`/api/predictions/history?limit=${encodeURIComponent(limit)}`),
  predictionEvidence: (id) => request(`/api/predictions/evidence/${encodeURIComponent(id)}`),
  recordPredictionOutcome: (id, body) => request(`/api/predictions/history/${encodeURIComponent(id)}/outcome`, { method: "POST", body }),
  predictionPlans: () => request("/api/predictions/plans"),
  savePredictionPlan: (body) => request("/api/predictions/plans", { method: "POST", body }),
  predictionSettings: () => request("/api/predictions/settings"),
  savePredictionSettings: (body) => request("/api/predictions/settings", { method: "PUT", body }),
  performanceModel: () => request("/api/performance/model"),
  performanceMapping: (studentId) => request(`/api/performance/mapping${studentId != null && studentId !== "" ? `?student_id=${encodeURIComponent(studentId)}` : ""}`),
  performancePredict: (body = {}) => request("/api/performance/predict", { method: "POST", body, timeoutMs: 15000 }),
  communityOverview: () => request("/api/communities/overview"),
  communities: (params = {}) => request(`/api/communities${academicQuery(params)}`),
  community: (id) => request(`/api/communities/${encodeURIComponent(id)}`),
  communityCategories: () => request("/api/communities/categories"),
  saveCommunityCategory: (body) => request("/api/communities/categories", { method: "POST", body }),
  communityPrivacy: () => request("/api/communities/privacy"),
  saveCommunityPrivacy: (body) => request("/api/communities/privacy", { method: "PUT", body }),
  communityFeed: (params = {}) => request(`/api/communities/feed${academicQuery(params)}`),
  recommendedCommunities: () => request("/api/communities/recommended"),
  similarCommunities: (body) => request("/api/communities/similar", { method: "POST", body }),
  communityRequests: () => request("/api/communities/requests"),
  createCommunityRequest: (body) => request("/api/communities/requests", { method: "POST", body }),
  updateCommunityRequest: (id, body) => request(`/api/communities/requests/${encodeURIComponent(id)}`, { method: "PATCH", body }),
  reviewCommunityRequest: (id, body) => request(`/api/communities/requests/${encodeURIComponent(id)}/review`, { method: "POST", body }),
  joinCommunity: (id) => request(`/api/communities/${encodeURIComponent(id)}/join`, { method: "POST" }),
  leaveCommunity: (id) => request(`/api/communities/${encodeURIComponent(id)}/leave`, { method: "DELETE" }),
  communityMembers: (id, params = {}) => request(`/api/communities/${encodeURIComponent(id)}/members${academicQuery(params)}`),
  communityPosts: (id, params = {}) => request(`/api/communities/${encodeURIComponent(id)}/posts${academicQuery(params)}`),
  createCommunityPost: (id, body) => request(`/api/communities/${encodeURIComponent(id)}/posts`, { method: "POST", body }),
  communityComments: (id, postId, params = {}) => request(`/api/communities/${encodeURIComponent(id)}/posts/${encodeURIComponent(postId)}/comments${academicQuery(params)}`),
  createCommunityComment: (id, postId, body) => request(`/api/communities/${encodeURIComponent(id)}/posts/${encodeURIComponent(postId)}/comments`, { method: "POST", body }),
  reactCommunityPost: (id, postId, body) => request(`/api/communities/${encodeURIComponent(id)}/posts/${encodeURIComponent(postId)}/reactions`, { method: "POST", body }),
  removeCommunityPost: (id, postId) => request(`/api/communities/${encodeURIComponent(id)}/posts/${encodeURIComponent(postId)}`, { method: "DELETE" }),
  communityEvents: (id) => request(`/api/communities/${encodeURIComponent(id)}/events`),
  createCommunityEvent: (id, body) => request(`/api/communities/${encodeURIComponent(id)}/events`, { method: "POST", body }),
  registerCommunityEvent: (id, eventId) => request(`/api/communities/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}/register`, { method: "POST" }),
  cancelCommunityEvent: (id, eventId) => request(`/api/communities/${encodeURIComponent(id)}/events/${encodeURIComponent(eventId)}/register`, { method: "DELETE" }),
  communityResources: (id) => request(`/api/communities/${encodeURIComponent(id)}/resources`),
  createCommunityResource: (id, body) => request(`/api/communities/${encodeURIComponent(id)}/resources`, { method: "POST", body }),
  createCommunityReport: (body) => request("/api/communities/reports", { method: "POST", body }),
  communityReports: (params = {}) => request(`/api/community-reports${academicQuery(params)}`),
  resolveCommunityReport: (id, body) => request(`/api/communities/reports/${encodeURIComponent(id)}/resolve`, { method: "POST", body }),
  setCommunityStatus: (id, body) => request(`/api/communities/${encodeURIComponent(id)}/status`, { method: "POST", body }),
  setCommunityRole: (id, body) => request(`/api/communities/${encodeURIComponent(id)}/roles`, { method: "POST", body }),
  blockCommunityStudent: (id) => request(`/api/communities/block/${encodeURIComponent(id)}`, { method: "POST" }),
  communityAnalytics: (id) => request(`/api/communities/${encodeURIComponent(id)}/analytics`),
};

function academicQuery(params = {}) {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      q.set(key, String(value));
    }
  });
  const text = q.toString();
  return text ? `?${text}` : "";
}

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
