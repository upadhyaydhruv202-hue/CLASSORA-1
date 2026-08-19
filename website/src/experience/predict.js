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
