/** Safe display helpers so nested API values never render as raw JSON. */

const SKIP_COLUMNS = new Set([
  "password",
  "token_hash",
  "face_embedding",
  "voice_embedding",
  "embedding",
  "bar",
  "logs",
  "explanation",
  "token",
]);

const CHANGE_LABELS = {
  attendance_delta: "Attendance",
  attendance_set: "Set attendance to",
  academic_delta: "Academic average",
  completion_delta: "Assignment completion",
  mentorship_active: "Mentorship",
  engagement_resume: "Engagement",
};

export function labelize(key) {
  return String(key || "")
    .replace(/([a-z])([A-Z])/g, "$1 $2")
    .replaceAll("_", " ")
    .replace(/\bid\b/gi, "ID")
    .replace(/^./, (ch) => ch.toUpperCase());
}

function looksLikeChanges(value) {
  const keys = Object.keys(value || {});
  if (!keys.length) return false;
  return keys.every((key) => (
    /_(delta|active|resume|set)$/.test(key)
    || key === "mentorship_active"
    || key === "engagement_resume"
  ));
}

export function formatChanges(changes) {
  if (!changes || typeof changes !== "object" || Array.isArray(changes)) return "—";
  const parts = Object.entries(changes)
    .filter(([, value]) => value !== false && value != null && value !== "")
    .map(([key, value]) => {
      const label = CHANGE_LABELS[key] || labelize(key);
      if (typeof value === "boolean") return value ? `${label} on` : null;
      if (typeof value === "number") {
        const sign = value > 0 ? "+" : "";
        return `${label} ${sign}${value} pp`;
      }
      return `${label} ${value}`;
    })
    .filter(Boolean);
  return parts.join(" · ") || "No change";
}

export function formatDateTime(value) {
  if (value == null || value === "") return "";
  const text = String(value).trim();
  if (!text) return "";
  if (!/^\d{4}-\d{2}-\d{2}/.test(text) && Number.isNaN(Date.parse(text))) return text;
  const parsed = new Date(text);
  if (Number.isNaN(parsed.getTime())) return text;
  return parsed.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function cellText(value) {
  if (value == null || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    return Number.isInteger(value) ? String(value) : String(value);
  }
  if (typeof value === "string") {
    const text = value.trim();
    if (!text) return "—";
    if (/^\d{4}-\d{2}-\d{2}T/.test(text)) {
      return formatDateTime(text) || text;
    }
    if ((text.startsWith("{") && text.endsWith("}")) || (text.startsWith("[") && text.endsWith("]"))) {
      try {
        return cellText(JSON.parse(text));
      } catch {
        return text;
      }
    }
    return text;
  }
  if (Array.isArray(value)) {
    if (!value.length) return "—";
    return value.map((item) => cellText(item)).filter((item) => item !== "—").join("; ") || "—";
  }
  if (typeof value === "object") {
    if (looksLikeChanges(value)) return formatChanges(value);
    if (value.name != null && (value.percent != null || value.share != null)) {
      const pct = value.percent ?? value.share;
      return `${value.name} (${pct}%)`;
    }
    for (const key of ["title", "name", "label", "subject_code", "recommendation", "message", "text", "body"]) {
      const item = value[key];
      if (item != null && typeof item !== "object") {
        const extra = value.section || value.code || value.category || value.status;
        return extra != null && typeof extra !== "object" ? `${item} (${extra})` : String(item);
      }
    }
    const parts = [];
    for (const [key, item] of Object.entries(value)) {
      if (SKIP_COLUMNS.has(key) || item == null || typeof item === "object") continue;
      parts.push(`${labelize(key)}: ${item}`);
      if (parts.length >= 4) break;
    }
    return parts.join(" · ") || "—";
  }
  return String(value);
}

export function flattenRecords(rows, columns) {
  const list = Array.isArray(rows) ? rows.filter((row) => row && typeof row === "object" && !Array.isArray(row)) : [];
  if (!list.length) return [];
  const keys = [];
  const seen = new Set();
  const preferred = columns?.length ? columns : Object.keys(list[0]);
  for (const key of preferred) {
    if (SKIP_COLUMNS.has(key) || seen.has(key)) continue;
    seen.add(key);
    keys.push(key);
  }
  if (!columns) {
    for (const row of list) {
      for (const key of Object.keys(row)) {
        if (SKIP_COLUMNS.has(key) || seen.has(key)) continue;
        seen.add(key);
        keys.push(key);
      }
    }
  }
  const visible = keys.filter((key) => list.some((row) => {
    const text = cellText(row[key]);
    return text !== "—";
  }));
  const use = visible.length ? visible : keys;
  return list.map((row) => {
    const out = {};
    for (const key of use) out[key] = cellText(row[key]);
    return out;
  }).filter((row) => Object.keys(row).length);
}

export function whyLines(twin, pred = {}) {
  const why = twin?.risk?.why;
  if (Array.isArray(why?.why) && why.why.length) {
    return why.why.map((line) => (typeof line === "string" ? line : cellText(line))).filter((line) => line && line !== "—");
  }
  const narrative = twin?.narrative?.why;
  if (Array.isArray(narrative) && narrative.length) {
    return narrative.map((line) => (typeof line === "string" ? line : line.label || line.text || cellText(line))).filter((line) => line && line !== "—");
  }
  return [];
}

export function driverList(twin, pred = {}) {
  return twin?.risk?.drivers || pred.drivers || [];
}

export function scenarioRows(scenarios = []) {
  return scenarios.map((row) => ({
    Scenario: row.title || row.name || row.id,
    "What changes": formatChanges(row.changes),
    Estimated: row.estimated_score ?? row.estimated,
    Category: row.estimated_category || row.category,
    Change: row.delta ?? row.improvement,
  }));
}

export function interventionRows(scenarios = []) {
  return scenarios.map((row) => ({
    Scenario: row.name || row.title,
    Estimated: row.estimated_score,
    Category: row.estimated_category,
    Change: row.delta,
    Direction: row.direction,
  }));
}

export function trajectoryRows(points = []) {
  return points.map((row) => ({
    Day: row.days == null ? "Now" : row.days,
    Score: row.score,
    Category: row.category,
    "Attendance drift": row.attendance_delta,
  }));
}

export function widgetLevelLabel(level) {
  return {
    LOW: "LOW RISK",
    MODERATE: "MODERATE RISK",
    HIGH: "HIGH RISK",
  }[String(level || "").toUpperCase()] || "RISK SCORE";
}
