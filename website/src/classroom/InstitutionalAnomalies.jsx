import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

function severityKind(value) {
  const key = String(value || "").toUpperCase();
  if (key === "CRITICAL") return "danger";
  if (key === "HIGH") return "warn";
  if (key === "MODERATE") return "info";
  return "muted";
}

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function formatNumber(value, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value)}${suffix}`;
}

function formatChange(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(1)} pp`;
}

function confidenceLabel(value) {
  if (value == null) return "—";
  if (typeof value === "string") {
    const key = value.toLowerCase();
    if (key === "insufficient") return "Insufficient evidence";
    if (key === "high") return "High confidence";
    if (key === "medium") return "Medium confidence";
    if (key === "low") return "Low confidence";
    return value;
  }
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  if (n >= 0.75) return `High (${Math.round(n * 100)}%)`;
  if (n >= 0.55) return `Medium (${Math.round(n * 100)}%)`;
  if (n >= 0.35) return `Low (${Math.round(n * 100)}%)`;
  return `Insufficient evidence`;
}

function TrendChart({ points = [], label = "Trend", highlightStart }) {
  const pts = (points || []).filter((p) => p && p.value != null);
  if (pts.length < 2) {
    return <p className="text-sm text-[#64748B]">Not enough historical points to draw this trend.</p>;
  }
  const w = 640;
  const h = 220;
  const pad = { t: 24, r: 20, b: 36, l: 44 };
  const xs = pts.map((_, i) => i);
  const ys = pts.map((p) => Number(p.value));
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(100, ...ys);
  const sx = (i) => pad.l + (i / Math.max(1, xs.length - 1)) * (w - pad.l - pad.r);
  const sy = (y) => pad.t + (1 - (y - minY) / Math.max(1, maxY - minY)) * (h - pad.t - pad.b);
  const d = pts.map((p, i) => `${i ? "L" : "M"}${sx(i)},${sy(Number(p.value))}`).join(" ");
  const ticks = [0, 25, 50, 75, 100].filter((tick) => tick >= minY && tick <= maxY);
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="co-chart" role="img" aria-label={`${label} historical trend`}>
      {ticks.map((tick) => (
        <g key={tick}>
          <line x1={pad.l} y1={sy(tick)} x2={w - pad.r} y2={sy(tick)} stroke="#E2E8F0" />
          <text x={pad.l - 8} y={sy(tick) + 4} textAnchor="end" fontSize="10" fill="#64748B">{tick}</text>
        </g>
      ))}
      <path d={d} fill="none" stroke="#2563EB" strokeWidth="2.4" strokeLinejoin="round" />
      {pts.map((p, i) => {
        const anomalous = highlightStart && String(p.start || "") >= String(highlightStart);
        return (
          <g key={`${p.start || i}`}>
            <circle cx={sx(i)} cy={sy(Number(p.value))} r={anomalous ? 5.5 : 4} fill={anomalous ? "#D97706" : "#2563EB"} />
            <text x={sx(i)} y={h - 12} textAnchor="middle" fontSize="9" fill="#64748B">{i + 1}</text>
          </g>
        );
      })}
    </svg>
  );
}

function HealthCards({ summary, onOpen }) {
  const items = [
    { label: "Active anomalies", value: summary.active },
    { label: "Critical", value: summary.critical },
    { label: "High", value: summary.high },
    { label: "Moderate", value: summary.moderate },
    { label: "Cohorts affected", value: summary.cohortsAffected },
    { label: "Students potentially affected", value: summary.studentsAffected },
    { label: "Recently resolved", value: summary.resolved },
  ];
  const top = summary.mostAffected;
  return (
    <div className="space-y-4">
      <div className="co-chips co-anomaly-chips">
        {items.map((item) => (
          <div key={item.label}>
            <em>{item.label}</em>
            <strong>{item.value ?? "—"}</strong>
          </div>
        ))}
      </div>
      {top && (
        <p className="text-sm text-[#64748B]">
          Most affected cohort: <strong className="text-[#0F172A]">{top.cohortLabel}</strong>
          {" · "}
          {String(top.metricType || "").replaceAll("_", " ")}
          {" · "}
          {formatChange(top.absoluteChange)}
        </p>
      )}
      {onOpen && (
        <button type="button" className="co-btn" onClick={onOpen}>View anomalies</button>
      )}
    </div>
  );
}

export function AnomalyHealthSummary({ summary, loading, error, onOpen }) {
  if (loading) {
    return <div className="co-resource-skel" aria-hidden="true" />;
  }
  if (error) {
    return <Notice title="Institutional anomalies unavailable" body={error} tone="danger" />;
  }
  if (!summary || summary.available === false) {
    return <EmptyState title="Anomaly analysis is currently unavailable." body="Authorized staff can retry after the service is reachable." />;
  }
  if (summary.coldStart && !summary.active) {
    return <EmptyState title="Insufficient historical data for reliable anomaly detection." body="CLASSORA needs enough comparable periods before it can flag unusual cohort changes." />;
  }
  return <HealthCards summary={summary} onOpen={onOpen} />;
}

const emptyFilters = {
  severity: "",
  status: "",
  section: "",
  semester: "",
  course: "",
  metric: "",
  cohort_type: "",
  search: "",
  sort: "newest",
  start: "",
  end: "",
};

export default function InstitutionalAnomalies({ session, variant = "page" }) {
  const role = session?.user_role;
  const canAnalyze = role === "administrator" || role === "teacher";
  const canAct = canAnalyze;
  const canConfigure = role === "administrator";
  const [summary, setSummary] = useState(null);
  const [list, setList] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filters, setFilters] = useState(emptyFilters);
  const [searchInput, setSearchInput] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [detail, setDetail] = useState(null);
  const [timeline, setTimeline] = useState(null);
  const [notes, setNotes] = useState([]);
  const [noteText, setNoteText] = useState("");
  const [settings, setSettings] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = async (nextFilters = filters) => {
    setLoading(true);
    setError("");
    try {
      const [sum, rows, cfg] = await Promise.all([
        api.anomalySummary(),
        api.anomalies(nextFilters),
        api.anomalySettings().catch(() => null),
      ]);
      setSummary(sum);
      setList(rows);
      if (cfg) setSettings(cfg);
    } catch (err) {
      setError(err.message || "Anomaly analysis is currently unavailable.");
      setList(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openDetail = async (id) => {
    setSelectedId(String(id));
    setBusy(true);
    try {
      const [one, trend, noteRows] = await Promise.all([
        api.anomaly(id),
        api.anomalyTimeline(id).catch(() => null),
        api.anomalyNotes(id).catch(() => ({ notes: [] })),
      ]);
      setDetail(one.anomaly || one);
      setTimeline(trend);
      setNotes(noteRows.notes || []);
    } catch (err) {
      setError(err.message || "Could not open this anomaly.");
    } finally {
      setBusy(false);
    }
  };

  const changeFilter = (key, value) => {
    const next = { ...filters, [key]: value };
    setFilters(next);
    load(next);
  };

  const applySearch = () => {
    const next = { ...filters, search: searchInput };
    setFilters(next);
    load(next);
  };

  const run = async (fn, okMessage) => {
    setBusy(true);
    setError("");
    try {
      await fn();
      if (okMessage) setNotice(okMessage);
      await load();
      if (selectedId) await openDetail(selectedId);
    } catch (err) {
      setError(err.message || "That action could not be completed.");
    } finally {
      setBusy(false);
    }
  };

  const anomalies = list?.anomalies;
  const sections = useMemo(() => [...new Set((anomalies || []).map((row) => row.section).filter(Boolean))], [anomalies]);
  const semesters = useMemo(() => [...new Set((anomalies || []).map((row) => row.semester).filter(Boolean))], [anomalies]);

  return (
    <div className={`co-anomalies ${variant === "embedded" ? "is-embedded" : ""}`}>
      <p className="co-section-kicker">Institutional intelligence</p>
      <h2 className="mb-1 text-[1.35rem] font-bold">Institutional Anomalies</h2>
      <p className="mb-4 text-sm text-[#64748B]">
        Unusual cohort-level changes compared with historical baseline. This does not replace individual student support-risk,
        and it does not assign a confirmed cause.
      </p>
      {notice && <Notice title="Updated" body={notice} tone="ok" />}
      {error && <Notice title="Something went wrong" body={error} tone="danger" />}

      {loading && (
        <div className="grid gap-3 md:grid-cols-3" aria-busy="true" aria-live="polite">
          <span className="sr-only">Loading institutional anomalies</span>
          <div className="co-resource-skel" />
          <div className="co-resource-skel" />
          <div className="co-resource-skel" />
        </div>
      )}

      {!loading && summary && (
        <AnomalyHealthSummary
          summary={summary}
          error=""
          onOpen={variant === "embedded" ? undefined : undefined}
        />
      )}

      <div className="co-resource-actions mt-4">
        {canAnalyze && (
          <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.analyzeAnomalies(), "Analysis finished.")}>
            Run analysis
          </button>
        )}
        <button type="button" className="co-btn co-btn-secondary" disabled={busy || loading} onClick={() => load()}>Refresh</button>
      </div>

      <div className="co-anomaly-filters">
        <Field label="Severity">
          <select className="co-input" value={filters.severity} onChange={(e) => changeFilter("severity", e.target.value)}>
            <option value="">All</option>
            {["CRITICAL", "HIGH", "MODERATE", "WATCH"].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </Field>
        <Field label="Status">
          <select className="co-input" value={filters.status} onChange={(e) => changeFilter("status", e.target.value)}>
            <option value="">All</option>
            {["NEW", "INVESTIGATING", "ACKNOWLEDGED", "RESOLVED", "DISMISSED"].map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </Field>
        <Field label="Section">
          <select className="co-input" value={filters.section} onChange={(e) => changeFilter("section", e.target.value)}>
            <option value="">All</option>
            {sections.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </Field>
        {semesters.length > 0 && (
          <Field label="Semester">
            <select className="co-input" value={filters.semester} onChange={(e) => changeFilter("semester", e.target.value)}>
              <option value="">All</option>
              {semesters.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </Field>
        )}
        <Field label="Metric">
          <select className="co-input" value={filters.metric} onChange={(e) => changeFilter("metric", e.target.value)}>
            <option value="">All</option>
            {["ATTENDANCE", "ASSIGNMENT", "MARKS", "ENGAGEMENT", "MULTI", "DATA_QUALITY"].map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
          </select>
        </Field>
        <Field label="Sort">
          <select className="co-input" value={filters.sort} onChange={(e) => changeFilter("sort", e.target.value)}>
            <option value="newest">Newest</option>
            <option value="severity">Severity</option>
            <option value="score">Anomaly score</option>
            <option value="affected">Affected students</option>
            <option value="affected_pct">Affected percentage</option>
          </select>
        </Field>
        <Field label="Search">
          <input className="co-input" value={searchInput} onChange={(e) => setSearchInput(e.target.value)} onBlur={applySearch} placeholder="Cohort, course, section" />
        </Field>
      </div>

      {!loading && !error && (anomalies || []).length === 0 && (
        <EmptyState
          title={summary?.coldStart ? "Insufficient historical data for reliable anomaly detection." : "No significant cohort anomalies detected."}
          body={summary?.coldStart ? "Keep recording attendance and assessments. The engine needs a comparable baseline." : "Current cohort metrics are within historical variation for the configured thresholds."}
        />
      )}

      {!loading && (anomalies || []).length > 0 && (
        <div className="co-table-wrap co-anomaly-table" role="region" aria-label="Active institutional anomalies">
          <table className="co-table">
            <thead>
              <tr>
                <th>Severity</th>
                <th>Cohort</th>
                <th>Metric</th>
                <th>Current</th>
                <th>Baseline</th>
                <th>Change</th>
                <th>Affected</th>
                <th>Confidence</th>
                <th>Detected</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {(anomalies || []).map((row) => (
                <tr key={row.id}>
                  <td>
                    <button type="button" className={`co-badge co-badge-${severityKind(row.severity)}`} onClick={() => openDetail(row.id)} aria-label={`${row.severity} anomaly for ${row.cohortLabel}`}>
                      {row.severity}
                    </button>
                  </td>
                  <td>
                    <button type="button" className="co-linkish" onClick={() => openDetail(row.id)}>{row.cohortLabel}</button>
                  </td>
                  <td>{String(row.metricType || "").replaceAll("_", " ")}</td>
                  <td>{formatNumber(row.currentValue)}</td>
                  <td>{formatNumber(row.baselineValue)}</td>
                  <td>{formatChange(row.absoluteChange)}</td>
                  <td>{row.affectedStudentCount} / {row.cohortSize} ({formatNumber(row.affectedPercentage, "%")})</td>
                  <td>{confidenceLabel(row.confidence)}</td>
                  <td>{formatWhen(row.detectedAt)}</td>
                  <td>{row.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {detail && (
        <section className="co-card mt-4" aria-labelledby="anomaly-detail-title">
          <p className="co-section-kicker">Investigation</p>
          <h3 id="anomaly-detail-title" className="mb-2 font-semibold">{detail.cohortLabel}</h3>
          <p className={`co-badge co-badge-${severityKind(detail.severity)}`}>{detail.severity}</p>
          <p className="mt-3 text-sm text-[#0F172A]">{detail.explanation}</p>
          <div className="co-chips mt-4">
            <div><em>Current</em><strong>{formatNumber(detail.currentValue)}</strong></div>
            <div><em>Baseline</em><strong>{formatNumber(detail.baselineValue)}</strong></div>
            <div><em>Change</em><strong>{formatChange(detail.absoluteChange)}</strong></div>
            <div><em>Impact</em><strong>{detail.affectedStudentCount} / {detail.cohortSize} ({formatNumber(detail.affectedPercentage, "%")})</strong></div>
            <div><em>Score</em><strong>{formatNumber(detail.anomalyScore)}</strong></div>
            <div><em>Confidence</em><strong>{confidenceLabel(detail.confidence)}</strong></div>
          </div>

          {(detail.metrics || []).length > 1 && (
            <div className="mt-4 space-y-3">
              {(detail.metrics || []).map((metric) => (
                <div key={metric.name}>
                  <p className="co-caption">{metric.label || metric.name}</p>
                  <p className="text-sm text-[#64748B]">
                    Current {formatNumber(metric.current)} · Baseline {formatNumber(metric.baseline)} · {formatChange(metric.ppChange)}
                  </p>
                  {timeline?.series?.[metric.name] && (
                    <TrendChart points={timeline.series[metric.name]} label={metric.label || metric.name} highlightStart={detail.windowStart} />
                  )}
                </div>
              ))}
            </div>
          )}
          {(detail.metrics || []).length <= 1 && timeline?.series && Object.keys(timeline.series).map((name) => (
            <div key={name} className="mt-4">
              <p className="co-caption">{engineLabel(name)}</p>
              <TrendChart points={timeline.series[name]} label={name} highlightStart={detail.windowStart} />
            </div>
          ))}

          {(detail.hierarchy || []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 font-semibold">Concentration</h4>
              <div className="co-table-wrap">
                <table className="co-table">
                  <thead>
                    <tr><th>Level</th><th>Cohort</th><th>Current</th><th>Baseline</th><th>Score</th><th>Affected</th></tr>
                  </thead>
                  <tbody>
                    {detail.hierarchy.map((row, i) => (
                      <tr key={`${row.cohortKey || i}`}>
                        <td>{row.cohortType}</td>
                        <td>{row.label}</td>
                        <td>{formatNumber(row.current)}</td>
                        <td>{formatNumber(row.baseline)}</td>
                        <td>{formatNumber(row.score)}</td>
                        <td>{formatNumber(row.affectedPct, "%")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {(detail.comparisons?.siblings || []).length > 0 && (
            <div className="mt-4">
              <h4 className="mb-2 font-semibold">Cohort comparison</h4>
              <ul className="text-sm text-[#334155]">
                {detail.comparisons.institution && (
                  <li>Institution: current {formatNumber(detail.comparisons.institution.current)} / baseline {formatNumber(detail.comparisons.institution.baseline)}</li>
                )}
                {detail.comparisons.siblings.map((row) => (
                  <li key={row.label}>{row.label}: current {formatNumber(row.current)} / baseline {formatNumber(row.baseline)} ({formatChange(row.ppChange)})</li>
                ))}
              </ul>
            </div>
          )}

          <div className="mt-4">
            <h4 className="mb-2 font-semibold">Possible contributing factors</h4>
            <p className="mb-2 text-sm text-[#64748B]">{detail.disclaimer}</p>
            <ol className="space-y-2 text-sm">
              {(detail.possibleCauses || []).map((cause, i) => (
                <li key={cause.id || i}>
                  <strong>{cause.title}</strong>
                  {" — "}
                  {confidenceLabel(cause.confidence)}
                  <p className="text-[#64748B]">{cause.why}</p>
                </li>
              ))}
            </ol>
          </div>

          {canAct && (
            <div className="co-resource-actions">
              <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => run(() => api.acknowledgeAnomaly(detail.id), "Marked acknowledged.")}>Acknowledge</button>
              <button type="button" className="co-btn co-btn-secondary" disabled={busy} onClick={() => run(() => api.investigateAnomaly(detail.id), "Marked investigating.")}>Investigate</button>
              <button type="button" className="co-btn" disabled={busy} onClick={() => run(() => api.resolveAnomaly(detail.id), "Marked resolved.")}>Mark resolved</button>
              <button type="button" className="co-btn co-btn-tertiary" disabled={busy} onClick={() => run(() => api.dismissAnomaly(detail.id), "Dismissed.")}>Dismiss</button>
            </div>
          )}

          {canAct && (
            <form className="mt-4" onSubmit={(e) => { e.preventDefault(); run(() => api.addAnomalyNote(detail.id, { note: noteText }).then(() => setNoteText("")), "Note saved."); }}>
              <Field label="Investigation note">
                <textarea className="co-input" rows={3} value={noteText} onChange={(e) => setNoteText(e.target.value)} placeholder="Record what was reviewed. Do not treat this as a confirmed cause." />
              </Field>
              <button type="submit" className="co-btn mt-2" disabled={busy || noteText.trim().length < 3}>Add note</button>
            </form>
          )}
          {notes.length > 0 && (
            <ul className="mt-3 space-y-2 text-sm">
              {notes.map((note) => (
                <li key={note.id}>
                  <strong>{note.actor || "Staff"}</strong> · {formatWhen(note.created_at)}
                  <p className="text-[#64748B]">{note.note}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {canConfigure && settings && (
        <section className="co-card mt-4">
          <h3 className="mb-2 font-semibold">Detection thresholds</h3>
          <p className="mb-3 text-sm text-[#64748B]">Changes apply to the next analysis run. They do not rewrite historical snapshots.</p>
          <SettingsForm settings={settings.settings || {}} busy={busy} onSave={(body) => run(() => api.saveAnomalySettings(body), "Thresholds saved.")} />
        </section>
      )}
    </div>
  );
}

function engineLabel(name) {
  return String(name || "").replaceAll("_", " ");
}

function SettingsForm({ settings, busy, onSave }) {
  const [form, setForm] = useState(settings);
  useEffect(() => setForm(settings), [settings]);
  const fields = [
    ["min_cohort_size", "Minimum cohort size"],
    ["min_baseline_periods", "Minimum baseline periods"],
    ["current_window_days", "Current window (days)"],
    ["baseline_weeks", "Baseline weeks"],
    ["min_affected_percent", "Minimum affected %"],
    ["min_anomaly_score", "Minimum anomaly score"],
    ["recovery_periods", "Recovery periods"],
  ];
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSave(form); }}>
      <div className="co-anomaly-filters">
        {fields.map(([key, label]) => (
          <Field key={key} label={label}>
            <input className="co-input" value={form[key] ?? ""} onChange={(e) => setForm({ ...form, [key]: e.target.value })} />
          </Field>
        ))}
      </div>
      <button type="submit" className="co-btn mt-3" disabled={busy}>Save thresholds</button>
    </form>
  );
}
