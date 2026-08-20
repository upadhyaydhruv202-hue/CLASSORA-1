export const APP_URL = "/app";
export const DEMO_URL =
  (typeof import.meta !== "undefined" && import.meta.env && (import.meta.env.VITE_DEMO_URL || import.meta.env.VITE_APP_URL)) ||
  APP_URL;

export const cineNav = [
  { id: "experience", label: "Experience" },
  { id: "ai-demo", label: "AI Demo" },
  { id: "how", label: "How It Works" },
  { id: "impact", label: "Impact" },
  { id: "technology", label: "Technology" },
];

export const pipeline = [
  { id: 0, kicker: "01", title: "Student Data", body: "Attendance, academics, assignments, and engagement from the enrolled roster." },
  { id: 1, kicker: "02", title: "Feature Analysis", body: "Gaps, consecutive absences, sudden decline, and missing-data flags." },
  { id: 2, kicker: "03", title: "ML Prediction", body: "A deterministic risk score. It is a support signal — not a diagnosis." },
  { id: 3, kicker: "04", title: "Explainable AI", body: "Every score arrives with factor contributions and confidence." },
  { id: 4, kicker: "05", title: "Intervention", body: "Human review decides. Nothing is automatic." },
];

export const interventions = [
  {
    id: "academic",
    title: "Academic Support",
    body: "Subject mentoring and targeted academic assistance after human review.",
    detail: "Pair the student with a subject mentor, reopen incomplete modules, and schedule two progress checks.",
  },
  {
    id: "attendance",
    title: "Attendance Support",
    body: "Early faculty follow-up and attendance monitoring — never silent.",
    detail: "Faculty outreach within 48 hours, absence pattern review, and a return-to-class plan.",
  },
  {
    id: "faculty",
    title: "Faculty Intervention",
    body: "Mentor assignment and regular progress reviews.",
    detail: "Assign a faculty mentor, log weekly reviews, and keep the counsellor in the loop.",
  },
  {
    id: "engagement",
    title: "Engagement Support",
    body: "Encourage participation and learning activity with counsellor approval.",
    detail: "Invite into discussion groups, restore LMS activity, and track participation — not punishment.",
  },
];

export const classroomStudents = [
  { id: 1024, name: "Stable", risk: "STABLE", attendance: 91, academic: 88, engagement: "High", assignments: 92 },
  { id: 1180, name: "Attention", risk: "ATTENTION", attendance: 74, academic: 68, engagement: "Medium", assignments: 71 },
  { id: 2048, name: "High Risk", risk: "HIGH", attendance: 62, academic: 54, engagement: "Low", assignments: 48 },
  { id: 2311, name: "Attention", risk: "ATTENTION", attendance: 71, academic: 61, engagement: "Low", assignments: 66 },
  { id: 2602, name: "Stable", risk: "STABLE", attendance: 94, academic: 82, engagement: "High", assignments: 89 },
];

export const networkStudents = [
  { id: 2048, risk: "HIGH", attendance: 62, academic: 54, status: "Pending review" },
  { id: 1180, risk: "ATTENTION", attendance: 74, academic: 68, status: "Faculty follow-up" },
  { id: 1024, risk: "STABLE", attendance: 91, academic: 88, status: "No action" },
  { id: 3310, risk: "HIGH", attendance: 58, academic: 51, status: "Mentor assigned" },
  { id: 2602, risk: "STABLE", attendance: 94, academic: 82, status: "No action" },
  { id: 2777, risk: "ATTENTION", attendance: 70, academic: 64, status: "Watchlist" },
];

export const techNodes = [
  { id: "data", label: "Student Data", tech: "Attendance · LMS · Academics", purpose: "Signals enter only from enrolled students — never invented GPA." },
  { id: "fe", label: "Frontend", tech: "React · Three.js / R3F", purpose: "This cinematic lab plus the Classora classroom portals." },
  { id: "api", label: "Backend / API", tech: "Python services", purpose: "Auth, RBAC, session persistence, and attendance write-guards." },
  { id: "ai", label: "AI Engine", tech: "Python · Scikit-learn", purpose: "Deterministic risk scoring isolated from face/voice identity." },
  { id: "db", label: "Database", tech: "PostgreSQL", purpose: "Roster, logs, and additive success schema." },
  { id: "pred", label: "Prediction", tech: "Explainable scoring", purpose: "Category, confidence, and missing-data warnings." },
  { id: "act", label: "Intervention", tech: "Human-in-the-loop", purpose: "Cases exist only after authorised review." },
];

export const impactCapabilities = [
  { key: "Attendance", body: "Teachers capture class photos or a short recording and match them to the enrolled roster." },
  { key: "Risk score", body: "A deterministic, inspectable support signal — not a diagnosis and not a black box." },
  { key: "Intervention", body: "Cases, mentorship, and complaints exist only after a human reviews them." },
  { key: "Roles", body: "Student FaceID, teacher register, and counsellor or admin Success Hub in one app." },
];

export const team = [
  {
    name: "Aum Pethani",
    role: "TEAM LEAD",
    github: "https://github.com/AumPethani05",
    linkedin: "https://www.linkedin.com/in/aum-pethani",
  },
  {
    name: "Dhruv Upadhyay",
    role: "TEAM CO-LEAD",
    github: "https://github.com/upadhyaydhruv202-hue",
    linkedin: "https://www.linkedin.com/in/dhruv-upadhyay-199287332/",
  },
  {
    name: "BashirAehmad Dedharotiya",
    role: "UI/UX DESIGNER",
    github: "https://github.com/TARBUZZ",
    linkedin: "https://www.linkedin.com/in/bashir-ahemad-471961354?utm_source=share_via&utm_content=profile&utm_medium=member_ios",
  },
  {
    name: "Krish Trivedi",
    role: "FRONTEND & PRESENTER",
    github: "https://github.com/Krishtrivedi8849",
    linkedin: "https://www.linkedin.com/in/krish-trivedi-740a67319?utm_source=share_via&utm_content=profile&utm_medium=member_android",
  },
  {
    name: "Sarvi Shah",
    role: "FRONTEND",
    github: "https://github.com/sarvishah",
    linkedin: "https://www.linkedin.com/in/sarvi-shah-75b996320/",
  },
  {
    name: "Jiya Shah",
    role: "R&D",
    github: "https://github.com/jiyashah0609",
    linkedin: "https://www.linkedin.com/in/jiya-undefined-39041242a/",
  },
];
