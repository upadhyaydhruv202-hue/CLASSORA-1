const WEIGHTS = {
  Attendance: 0.3,
  "Academic Performance": 0.25,
  Assignments: 0.2,
  Engagement: 0.15,
  "Attendance Trend": 0.1,
};

const SCALE = 1.67;

function engagementValue(engagement) {
  return engagement === "LOW" ? 28 : engagement === "MEDIUM" ? 58 : 84;
}

function trendValue(trend) {
  return trend === "DECLINING" ? 20 : trend === "STABLE" ? 58 : 86;
}

export function predict({ attendance, academic, assignments, engagement, trend }) {
  const eng = engagementValue(engagement);
  const tr = trendValue(trend);
  const gaps = {
    Attendance: 100 - attendance,
    "Academic Performance": 100 - academic,
    Assignments: 100 - assignments,
    Engagement: 100 - eng,
    "Attendance Trend": 100 - tr,
  };
  const raw = Object.entries(gaps).reduce((s, [k, v]) => s + v * WEIGHTS[k], 0);
  const score = Math.round(Math.min(97, Math.max(6, raw * SCALE)));
  const total = raw || 1;
  const factors = Object.entries(gaps).map(([k, v]) => ({
    key: k,
    contribution: Math.round(((v * WEIGHTS[k]) / total) * 100),
    weight: Math.round(WEIGHTS[k] * 100),
    detail:
      k === "Attendance"
        ? "Presence gaps and consecutive absences are the strongest early warning signal."
        : k === "Academic Performance"
          ? "Assessment scores are associated factors — not a diagnosis."
          : k === "Assignments"
            ? "Incomplete work often arrives before the student disappears from class."
            : k === "Engagement"
              ? "Low participation is a support signal, not a character judgment."
              : "A declining trajectory raises estimated risk even when a single week looks fine.",
  }));
  const band = score >= 70 ? "HIGH DROPOUT RISK" : score >= 45 ? "NEEDS ATTENTION" : "STABLE";
  return { score, band, factors, raw };
}

export const DEFAULTS = {
  attendance: 62,
  academic: 54,
  assignments: 48,
  engagement: "LOW",
  trend: "DECLINING",
};

export const RECOVERED = {
  attendance: 86,
  academic: 78,
  assignments: 81,
  engagement: "HIGH",
  trend: "IMPROVING",
};

export function riskTone(score, sim = 0) {
  const v = score * (1 - Math.min(sim, 1) * 0.72);
  if (v >= 70) return { key: "high", hex: "#ef4444" };
  if (v >= 45) return { key: "mid", hex: "#f59e0b" };
  return { key: "low", hex: "#22c55e" };
}

export function formFromStudent(student) {
  const engagement = String(student.engagement || "MEDIUM").toUpperCase();
  return {
    attendance: student.attendance,
    academic: student.academic,
    assignments: student.assignments,
    engagement: engagement === "HIGH" || engagement === "LOW" ? engagement : "MEDIUM",
    trend: student.risk === "HIGH" ? "DECLINING" : student.risk === "STABLE" ? "STABLE" : "STABLE",
  };
}

const INTERVENTION_BLEND = {
  academic: { attendance: 0.08, academic: 1, assignments: 0.72, engagement: 0.22, trend: 0.12 },
  attendance: { attendance: 1, academic: 0.1, assignments: 0.12, engagement: 0.18, trend: 1 },
  faculty: { attendance: 0.22, academic: 0.55, assignments: 0.45, engagement: 0.7, trend: 0.5 },
  engagement: { attendance: 0.1, academic: 0.2, assignments: 0.55, engagement: 1, trend: 0.28 },
};

function blendNum(from, to, t) {
  return Math.round(from + (to - from) * t);
}

function blendEngagement(from, to, t) {
  if (t >= 0.55) return to;
  if (t >= 0.25 && from !== to) return "MEDIUM";
  return from;
}

function blendTrend(from, to, t) {
  return t >= 0.4 ? to : from;
}

export function applyIntervention(form, id) {
  const w = INTERVENTION_BLEND[id];
  if (!w) return { ...form };
  return {
    attendance: blendNum(form.attendance, RECOVERED.attendance, w.attendance),
    academic: blendNum(form.academic, RECOVERED.academic, w.academic),
    assignments: blendNum(form.assignments, RECOVERED.assignments, w.assignments),
    engagement: blendEngagement(form.engagement, RECOVERED.engagement, w.engagement),
    trend: blendTrend(form.trend, RECOVERED.trend, w.trend),
  };
}

export function compareInterventions(form, ids) {
  const current = predict(form).score;
  return ids.map((id) => {
    const projected = predict(applyIntervention(form, id)).score;
    return { id, current, projected, improvement: Math.max(0, current - projected) };
  });
}

export function combinedProjection(form) {
  const current = predict(form).score;
  const projected = predict(RECOVERED).score;
  return { current, projected, improvement: Math.max(0, current - projected) };
}
