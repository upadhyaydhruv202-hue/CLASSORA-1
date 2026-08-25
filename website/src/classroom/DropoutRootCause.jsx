import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

function formatNumber(value, suffix = "") {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return `${Number(value)}${suffix}`;
}

function formatChange(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  const n = Number(value);
  return `${n > 0 ? "+" : ""}${n.toFixed(1)} pp`;
}

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function classKind(value) {
  const key = String(value || "").toUpperCase();
  if (key === "SIGNIFICANT" || key === "CRITICAL" || key === "HIGH") return "danger";
  if (key === "EMERGING" || key === "MODERATE") return "warn";
  if (key === "INSUFFICIENT_DATA" || key === "NOT_AVAILABLE") return "muted";
  return "info";
}

function TrendChart({ points = [], label = "Dropout rate" }) {
  const pts = (points || []).filter((p) => p && p.value != null);
  if (pts.length < 2) {
    return <p className="text-sm text-[#64748B]">Not enough historical points to draw this trend.</p>;
  }
  const w = 640;
  const h = 220;
  const pad = { t: 24, r: 20, b: 36, l: 44 };
  const ys = pts.map((p) => Number(p.value));
  const minY = Math.min(0, ...ys);
  const maxY = Math.max(Math.max(...ys, 10), 1);
  const sx = (i) => pad.l + (i / Math.max(1, pts.length - 1)) * (w - pad.l - pad.r);
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
      {pts.map((p, i) => (
        <g key={`${p.label || i}`}>
          <circle cx={sx(i)} cy={sy(Number(p.value))} r="4" fill="#2563EB" />
          <text x={sx(i)} y={h - 12} textAnchor="middle" fontSize="9" fill="#64748B">{p.label || i + 1}</text>
        </g>
      ))}
    </svg>
  );
}

function FactorBars({ factors = [] }) {
  const rows = (factors || []).filter((f) => f.dropoutRate != null).slice(0, 8);
  if (!rows.length) return <p className="text-sm text-[#64748B]">No ranked factors with enough data.</p>;
  const max = Math.max(...rows.map((f) => Number(f.dropoutRate) || 0), 1);
  return (
    <div className="co-dropout-bars" role="img" aria-label="Ranked dropout-associated factors">
      {rows.map((factor) => (
        <div key={factor.factorId} className="co-dropout-bar-row">
          <span>{factor.factorName}</span>
          <div className="co-dropout-bar-track" aria-hidden="true">
            <div style={{ width: `${Math.max(4, (Number(factor.dropoutRate) / max) * 100)}%` }} />
          </div>
          <strong>{formatNumber(factor.dropoutRate, "%")}</strong>
        </div>
      ))}
    </div>
  );
}

function Heatmap({ cells = [], onSelect }) {
  const rows = [...new Set((cells || []).map((c) => c.section))];
  const cols = [...new Set((cells || []).map((c) => c.semester))];
  if (!rows.length || !cols.length) {
    return <p className="text-sm text-[#64748B]">No section × semester cells are available.</p>;
  }
  const rates = cells.map((c) => Number(c.dropoutRate)).filter((n) => !Number.isNaN(n));
  const max = Math.max(...rates, 1);
  return (
    <div className="co-heatmap-wrap" role="table" aria-label="Section by semester dropout rate heatmap">
      <div className="co-heatmap" style={{ gridTemplateColumns: `8rem repeat(${cols.length}, minmax(4.5rem, 1fr))` }}>
        <div className="co-heatmap-head" />
        {cols.map((col) => <div key={col} className="co-heatmap-head">{col}</div>)}
        {rows.map((row) => [
          <div key={`${row}-label`} className="co-heatmap-head">{row}</div>,
          ...cols.map((col) => {
            const cell = cells.find((c) => c.section === row && c.semester === col);
            const rate = cell?.dropoutRate;
            const suppressed = cell?.suppressed;
            const intensity = rate == null ? 0 : Math.min(1, Number(rate) / max);
            return (
              <button
                key={`${row}-${col}`}
                type="button"
                className="co-heatmap-cell"
                style={{ background: suppressed ? "#E2E8F0" : `rgba(37, 99, 235, ${0.12 + intensity * 0.7})`, color: intensity > 0.55 ? "#fff" : "#0F172A" }}
                onClick={() => cell && onSelect?.(cell)}
                aria-label={suppressed ? `${row} ${col} suppressed` : `${row} ${col} dropout rate ${rate ?? "unavailable"} percent`}
              >
                {suppressed ? "—" : formatNumber(rate, "%")}
              </button>
            );
          }),
        ])}
      </div>
      <p className="text-sm text-[#64748B]">Color intensity follows observed dropout rate. Values are also shown as text.</p>
    </div>
  );
}

function SliceTable({ rows = [], onOpen, empty = "No rows in this grouping." }) {
  const visible = rows || [];
  if (!visible.length) return <EmptyState title={empty} />;
  return (
    <div className="co-table-wrap co-anomaly-table">
      <table className="co-table">
        <thead>
          <tr>
            <th>Group</th>
            <th>Students</th>
            <th>Dropouts</th>
            <th>Rate</th>
            <th>vs institution</th>
            <th>Priority</th>
          </tr>
        </thead>
        <tbody>
          {visible.map((row) => (
            <tr key={row.id}>
              <td>
                {row.suppressed ? row.label : (
                  <button type="button" className="co-linkish" onClick={() => onOpen?.(row)}>{row.label}</button>
                )}
              </td>
              <td>{row.suppressed ? "Suppressed" : formatNumber(row.students)}</td>
              <td>{row.suppressed ? "—" : formatNumber(row.dropouts)}</td>
              <td>{row.suppressed ? "—" : formatNumber(row.dropoutRate, "%")}</td>
              <td>{row.suppressed ? "—" : formatChange(row.vsInstitution)}</td>
              <td>{row.suppressed ? "—" : row.priority || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function OverviewCards({ overview }) {
  const items = [
    { label: "Enrolled", value: overview?.enrolled },
    { label: "Observed dropouts", value: overview?.dropouts },
    { label: "Institutional dropout rate", value: overview?.dropoutRate != null ? `${overview.dropoutRate}%` : null },
    { label: "Change vs previous period", value: formatChange(overview?.changePp) },
    { label: "Highest-volume section", value: overview?.highestSection?.label },
    { label: "Highest-volume semester", value: overview?.highestSemester?.label },
    { label: "Top associated factor", value: overview?.topFactor?.factorName },
  ];
  return (
    <div className="co-chips co-anomaly-chips">
      {items.map((item) => (
        <div key={item.label}>
          <em>{item.label}</em>
          <strong>{item.value ?? "—"}</strong>
        </div>
      ))}
    </div>
  );
}

export function DropoutHealthSummary({ summary, loading, error, onOpen }) {
  if (loading) return <div className="co-resource-skel" aria-hidden="true" />;
  if (error) return <Notice title="Dropout intelligence unavailable" body={error} tone="danger" />;
  if (!summary || summary.available === false) {
    return <EmptyState title="Dropout analysis is currently unavailable." body="Authorized leadership can retry after the service is reachable." />;
  }
  if (!summary.hasAnalysis || summary.insufficient) {
    return (
      <EmptyState
        title="Insufficient historical dropout data for reliable institutional root-cause analysis."
        body={summary.reason || "Run analysis after explicit academic outcomes are recorded."}
      />
    );
  }
  return (
    <div className="space-y-3">
      <div className="co-chips co-anomaly-chips">
        <div><em>Dropout rate</em><strong>{formatNumber(summary.dropoutRate, "%")}</strong></div>
        <div><em>Observed dropouts</em><strong>{formatNumber(summary.dropouts)}</strong></div>
        <div><em>Enrolled</em><strong>{formatNumber(summary.enrolled)}</strong></div>
        <div><em>Change</em><strong>{formatChange(summary.changePp)}</strong></div>
        <div><em>Top associated factor</em><strong>{summary.topFactor?.factorName || "—"}</strong></div>
      </div>
      <p className="text-sm text-[#64748B]">{summary.disclaimer}</p>
      {onOpen && <button type="button" className="co-btn" onClick={onOpen}>Open dropout root causes</button>}
    </div>
  );
}

function downloadRows(filename, rows) {
  if (!rows?.length) return;
  const keys = Object.keys(rows[0]);
  const escape = (value) => `"${String(value ?? "").replaceAll('"', '""')}"`;
  const lines = [keys.join(","), ...rows.map((row) => keys.map((key) => escape(row[key])).join(","))];
  const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export default function DropoutRootCause({ session, variant = "page" }) {
  const role = session?.user_role;
  const canAnalyze = role === "administrator" || role === "teacher";
  const canConfigure = role === "administrator";
  const [overview, setOverview] = useState(null);
  const [factors, setFactors] = useState(null);
  const [trends, setTrends] = useState([]);
  const [heatmap, setHeatmap] = useState([]);
  const [sections, setSections] = useState([]);
  const [semesters, setSemesters] = useState([]);
  const [courses, setCourses] = useState([]);
  const [intersections, setIntersections] = useState([]);
  const [recommendations, setRecommendations] = useState([]);
  const [settings, setSettings] = useState(null);
  const [selected, setSelected] = useState(null);
  const [compare, setCompare] = useState(null);
  const [firstYear, setFirstYear] = useState(null);
  const [outcomes, setOutcomes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [filters, setFilters] = useState({ factor: "", classification: "", confidence: "" });
  const [cmp, setCmp] = useState({ kind: "section", left: "", right: "" });
  const [outcomeForm, setOutcomeForm] = useState({ student_id: "", status: "DROPPED_OUT", period: "", notes: "" });
  const [deptNote, setDeptNote] = useState("");

  const load = async (nextFilters = filters) => {
    setLoading(true);
    setError("");
    try {
      if (variant === "embedded") {
        const ov = await api.dropoutOverview();
        setOverview(ov);
        return;
      }
      const [ov, fac, tr, hm, dep, sem, crs, inter, rec, cfg] = await Promise.all([
        api.dropoutOverview(),
        api.dropoutFactors(nextFilters),
        api.dropoutTrends(),
        api.dropoutHeatmap(),
        api.dropoutDepartments(),
        api.dropoutSemesters(),
        api.dropoutCourses(),
        api.dropoutIntersections(),
        api.dropoutRecommendations(),
        api.dropoutSettings().catch(() => null),
      ]);
      setOverview(ov);
      setFactors(fac);
      setTrends(tr.trends || []);
      setHeatmap(hm.heatmap || []);
      setSections(dep.sections || []);
      setDeptNote(dep.reason || "");
      setSemesters(sem.semesters || []);
      setCourses(crs.courses || []);
      setIntersections(inter.intersections || []);
      setRecommendations(rec.recommendations || []);
      if (cfg) setSettings(cfg);
      if (canConfigure) {
        const listed = await api.dropoutOutcomes().catch(() => ({ outcomes: [] }));
        setOutcomes(listed.outcomes || []);
      }
      api.dropoutFirstYear().then(setFirstYear).catch(() => setFirstYear(null));
    } catch (err) {
      setError(err.message || "Dropout analysis is currently unavailable.");
      setOverview(null);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const openFactor = async (id) => {
    try {
      const data = await api.dropoutFactor(id);
      setSelected(data.factor);
    } catch (err) {
      setNotice(err.message || "Could not open that factor.");
    }
  };

  const runAnalyze = async () => {
    setBusy(true);
    setNotice("");
    try {
      const result = await api.analyzeDropout();
      setNotice(result.insufficient
        ? (result.reason || "Insufficient historical dropout data for reliable institutional root-cause analysis.")
        : "Analysis updated from current institutional records.");
      await load();
    } catch (err) {
      setError(err.message || "Dropout analysis is currently unavailable.");
    } finally {
      setBusy(false);
    }
  };

  const runCompare = async () => {
    setBusy(true);
    try {
      const row = await api.dropoutCompare(cmp);
      setCompare(row);
    } catch (err) {
      setNotice(err.message || "Comparison is unavailable.");
      setCompare(null);
    } finally {
      setBusy(false);
    }
  };

  const exportCsv = async () => {
    try {
      const report = await api.dropoutReport();
      const rows = (report.factors || []).map((factor) => ({
        factor: factor.factorName,
        students: factor.affectedStudents,
        dropouts: factor.affectedDropouts,
        dropoutRate: factor.dropoutRate,
        relativeRisk: factor.relativeRisk,
        riskDifference: factor.riskDifference,
        confidence: factor.confidence,
        evidence: factor.evidence,
      }));
      downloadRows("institutional-dropout.csv", rows);
    } catch (err) {
      setNotice(err.message || "Export is unavailable.");
    }
  };

  const saveSettings = async () => {
    setBusy(true);
    try {
      await api.saveDropoutSettings(settings.settings || {});
      setNotice("Thresholds updated.");
    } catch (err) {
      setNotice(err.message || "Could not save settings.");
    } finally {
      setBusy(false);
    }
  };

  const recordOutcome = async () => {
    setBusy(true);
    try {
      await api.recordDropoutOutcome({
        student_id: Number(outcomeForm.student_id),
        status: outcomeForm.status,
        period: outcomeForm.period,
        notes: outcomeForm.notes,
      });
      setNotice("Academic outcome recorded. Run analysis to refresh associations.");
      setOutcomeForm({ ...outcomeForm, student_id: "", notes: "" });
      await load();
    } catch (err) {
      setNotice(err.message || "Could not record that outcome.");
    } finally {
      setBusy(false);
    }
  };

  const trendPoints = useMemo(
    () => (trends || []).map((row) => ({ label: row.period, value: row.dropoutRate })),
    [trends],
  );

  if (variant === "embedded") {
    return (
      <DropoutHealthSummary
        summary={overview ? {
          available: overview.available,
          hasAnalysis: overview.hasAnalysis,
          insufficient: overview.insufficient,
          reason: overview.reason,
          dropoutRate: overview.overview?.dropoutRate,
          dropouts: overview.overview?.dropouts,
          enrolled: overview.overview?.enrolled,
          changePp: overview.overview?.changePp,
          topFactor: overview.overview?.topFactor,
          disclaimer: overview.disclaimer,
        } : null}
        loading={loading}
        error={error}
      />
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">Institutional Intelligence</p>
        <h2 className="text-xl font-semibold">Dropout Root Causes</h2>
        <p className="text-sm text-[#64748B]">
          Associated factors from explicit academic outcomes. This does not replace individual risk scores and does not claim causation.
        </p>
      </div>

      {notice && <Notice title="Update" body={notice} tone="info" />}
      {error && <Notice title="Dropout analysis unavailable" body={error} tone="danger" />}

      <div className="flex flex-wrap gap-2">
        {canAnalyze && <button type="button" className="co-btn" disabled={busy || loading} onClick={runAnalyze}>{busy ? "Analyzing…" : "Run analysis"}</button>}
        <button type="button" className="co-btn" disabled={loading} onClick={() => load()}>Refresh</button>
        <button type="button" className="co-btn" disabled={!overview?.hasAnalysis || overview?.insufficient} onClick={exportCsv}>Export CSV</button>
      </div>

      {loading && (
        <div className="space-y-3" aria-busy="true" aria-live="polite">
          <div className="co-resource-skel" />
          <div className="co-resource-skel" />
          <p className="text-sm text-[#64748B]">Loading institutional dropout analysis…</p>
        </div>
      )}

      {!loading && overview && !overview.hasAnalysis && (
        <EmptyState title="No analysis has been run yet." body="Authorized administrators or faculty can run analysis after explicit dropout outcomes exist." />
      )}

      {!loading && overview?.hasAnalysis && overview.insufficient && (
        <EmptyState
          title="Insufficient historical dropout data for reliable institutional root-cause analysis."
          body={overview.reason || "CLASSORA does not invent dropouts from risk scores. Record explicit academic outcomes first."}
        />
      )}

      {!loading && overview?.hasAnalysis && !overview.insufficient && (
        <>
          {overview.scopeNote && <Notice title="Access scope" body={overview.scopeNote} tone="info" />}
          <OverviewCards overview={overview.overview} />
          {overview.story && <Notice title="Evidence summary" body={overview.story} tone="info" />}
          {overview.noDominantFactor && <Notice title="No dominant factor" body={overview.emptyMessage} tone="info" />}
          <p className="text-sm text-[#64748B]">{overview.disclaimer}</p>
          {overview.definition?.note && <p className="text-sm text-[#64748B]">{overview.definition.note}</p>}

          <div className="co-card">
            <h3 className="mb-3 font-semibold">Historical dropout rate</h3>
            <TrendChart points={trendPoints} label="Institutional dropout rate" />
          </div>

          <div className="co-card">
            <h3 className="mb-3 font-semibold">Top dropout-associated factors</h3>
            <div className="co-anomaly-filters">
              <Field label="Factor">
                <input className="co-input" value={filters.factor} onChange={(e) => setFilters({ ...filters, factor: e.target.value })} />
              </Field>
              <Field label="Classification">
                <select className="co-input" value={filters.classification} onChange={(e) => setFilters({ ...filters, classification: e.target.value })}>
                  <option value="">All</option>
                  <option value="SIGNIFICANT">Significant</option>
                  <option value="MODERATE">Moderate</option>
                  <option value="EMERGING">Emerging</option>
                  <option value="STABLE">Stable</option>
                  <option value="DECLINING">Declining</option>
                  <option value="INSUFFICIENT_DATA">Insufficient data</option>
                </select>
              </Field>
              <Field label="Confidence">
                <select className="co-input" value={filters.confidence} onChange={(e) => setFilters({ ...filters, confidence: e.target.value })}>
                  <option value="">All</option>
                  <option value="HIGH">High</option>
                  <option value="MODERATE">Moderate</option>
                  <option value="LOW">Low</option>
                  <option value="INSUFFICIENT_DATA">Insufficient data</option>
                </select>
              </Field>
            </div>
            <button type="button" className="co-btn mb-3" onClick={() => load(filters)}>Apply filters</button>
            <FactorBars factors={factors?.factors || []} />
            <div className="co-table-wrap co-anomaly-table">
              <table className="co-table">
                <thead>
                  <tr>
                    <th>Factor</th>
                    <th>Students</th>
                    <th>Dropouts</th>
                    <th>Rate</th>
                    <th>Relative risk</th>
                    <th>Risk difference</th>
                    <th>Confidence</th>
                    <th>Class</th>
                  </tr>
                </thead>
                <tbody>
                  {(factors?.factors || []).map((factor) => (
                    <tr key={factor.factorId}>
                      <td>
                        <button type="button" className="co-linkish" onClick={() => openFactor(factor.factorId)}>{factor.factorName}</button>
                      </td>
                      <td>{formatNumber(factor.affectedStudents)}</td>
                      <td>{formatNumber(factor.affectedDropouts)}</td>
                      <td>{formatNumber(factor.dropoutRate, "%")}</td>
                      <td>{factor.relativeRisk != null ? `${factor.relativeRisk}×` : "—"}</td>
                      <td>{formatChange(factor.riskDifference)}</td>
                      <td>{factor.confidence || "—"}</td>
                      <td><span className={`co-pill ${classKind(factor.classification)}`}>{factor.classification}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {selected && (
            <div className="co-card">
              <h3 className="mb-2 font-semibold">{selected.factorName}</h3>
              <p className="text-sm text-[#64748B]">{selected.evidence}</p>
              <div className="co-chips co-anomaly-chips mt-3">
                <div><em>Students affected</em><strong>{formatNumber(selected.affectedStudents)}</strong></div>
                <div><em>Dropouts</em><strong>{formatNumber(selected.affectedDropouts)}</strong></div>
                <div><em>Dropout rate</em><strong>{formatNumber(selected.dropoutRate, "%")}</strong></div>
                <div><em>Institution baseline</em><strong>{formatNumber(selected.baselineDropoutRate, "%")}</strong></div>
                <div><em>Relative risk</em><strong>{selected.relativeRisk != null ? `${selected.relativeRisk}× higher observed dropout rate` : "—"}</strong></div>
                <div><em>Confidence</em><strong>{selected.confidence}</strong></div>
              </div>
              {selected.trends?.length > 1 && (
                <TrendChart points={selected.trends.map((row) => ({ label: row.period, value: row.rate }))} label={`${selected.factorName} dropout rate`} />
              )}
              {selected.drilldown && (
                <div className="mt-4 space-y-3">
                  <h4 className="font-semibold">Where this factor is concentrated</h4>
                  <SliceTable rows={selected.drilldown.sections} />
                  <SliceTable rows={selected.drilldown.semesters} />
                  <SliceTable rows={selected.drilldown.courses} />
                </div>
              )}
            </div>
          )}

          <div className="co-card">
            <h3 className="mb-3 font-semibold">Section × semester heatmap</h3>
            <Heatmap cells={heatmap} onSelect={(cell) => setNotice(`Section ${cell.section}, semester ${cell.semester}: observed rate ${formatNumber(cell.dropoutRate, "%")}.`)} />
          </div>

          <div className="co-card">
            <h3 className="mb-2 font-semibold">Sections</h3>
            {deptNote && <p className="mb-2 text-sm text-[#64748B]">{deptNote}</p>}
            <SliceTable rows={sections} />
          </div>
          <div className="co-card">
            <h3 className="mb-2 font-semibold">Semesters</h3>
            <SliceTable rows={semesters} />
          </div>
          <div className="co-card">
            <h3 className="mb-2 font-semibold">Courses</h3>
            <SliceTable rows={courses} />
          </div>

          {firstYear?.available && (
            <div className="co-card">
              <h3 className="mb-2 font-semibold">First-year concentration</h3>
              <p className="text-sm text-[#64748B]">
                First-year / early-semester records account for {formatNumber(firstYear.shareOfDropouts, "%")} of observed dropouts.
                This is a concentration pattern, not a confirmed cause.
              </p>
            </div>
          )}
          {firstYear?.unavailable && (
            <Notice title="First-year analysis not available" body={firstYear.unavailable.reason} tone="info" />
          )}

          <div className="co-card">
            <h3 className="mb-2 font-semibold">Factor intersections</h3>
            {(intersections || []).map((item) => (
              <p key={item.id} className="mb-2 text-sm text-[#334155]">{item.evidence || item.id}</p>
            ))}
          </div>

          <div className="co-card">
            <h3 className="mb-2 font-semibold">Intervention priorities</h3>
            {(recommendations || []).length === 0 && <EmptyState title="No evidence-based recommendations in this period." />}
            {(recommendations || []).map((item) => (
              <div key={item.factorId} className="mb-3">
                <strong>Priority {item.priority}: {item.title}</strong>
                <p className="text-sm text-[#64748B]">{item.recommendation}</p>
                <p className="text-sm text-[#94A3B8]">{item.note}</p>
              </div>
            ))}
          </div>

          <div className="co-card">
            <h3 className="mb-3 font-semibold">Compare groups</h3>
            <div className="co-anomaly-filters">
              <Field label="Kind">
                <select className="co-input" value={cmp.kind} onChange={(e) => setCmp({ ...cmp, kind: e.target.value, left: "", right: "" })}>
                  <option value="section">Section</option>
                  <option value="semester">Semester</option>
                  <option value="course">Course</option>
                  <option value="period">Period</option>
                </select>
              </Field>
              <Field label="Left">
                <input className="co-input" value={cmp.left} onChange={(e) => setCmp({ ...cmp, left: e.target.value })} placeholder="id or period" />
              </Field>
              <Field label="Right">
                <input className="co-input" value={cmp.right} onChange={(e) => setCmp({ ...cmp, right: e.target.value })} placeholder="id or period" />
              </Field>
            </div>
            <button type="button" className="co-btn" disabled={busy} onClick={runCompare}>Compare</button>
            {compare && (
              <p className="mt-3 text-sm text-[#334155]">
                {compare.left?.label || compare.left?.period}: {formatNumber(compare.left?.dropoutRate, "%")} vs {compare.right?.label || compare.right?.period}: {formatNumber(compare.right?.dropoutRate, "%")}.
                Difference {formatChange(compare.rateDifference)}. {compare.note}
              </p>
            )}
          </div>

          <div className="co-card">
            <h3 className="mb-2 font-semibold">Unsupported factors</h3>
            {Object.entries(overview.unavailable || {}).map(([key, item]) => (
              <p key={key} className="text-sm text-[#64748B]"><strong>{key}</strong>: {item.reason} ({item.status || "NOT_AVAILABLE"})</p>
            ))}
          </div>
        </>
      )}

      {canConfigure && settings && (
        <div className="co-card">
          <h3 className="mb-3 font-semibold">Analysis thresholds</h3>
          <div className="co-anomaly-filters">
            {["min_factor_sample_size", "min_dropout_observations", "suppress_group_size", "low_attendance_threshold", "fail_mark", "high_rate_threshold", "high_volume_threshold"].map((key) => (
              <Field key={key} label={key.replaceAll("_", " ")}>
                <input
                  className="co-input"
                  type="number"
                  value={settings.settings?.[key] ?? ""}
                  onChange={(e) => setSettings({
                    ...settings,
                    settings: { ...settings.settings, [key]: e.target.value === "" ? "" : Number(e.target.value) },
                  })}
                />
              </Field>
            ))}
          </div>
          <button type="button" className="co-btn" disabled={busy} onClick={saveSettings}>Save thresholds</button>
          <p className="mt-2 text-sm text-[#64748B]">Last analysis: {formatWhen(settings.lastAnalysisAt)}</p>
        </div>
      )}

      {canConfigure && (
        <div className="co-card">
          <h3 className="mb-2 font-semibold">Record academic outcomes</h3>
          <p className="mb-3 text-sm text-[#64748B]">
            CLASSORA has no built-in dropout field. Record explicit statuses here. Risk scores are not treated as dropouts.
          </p>
          <div className="co-anomaly-filters">
            <Field label="Student ID">
              <input className="co-input" value={outcomeForm.student_id} onChange={(e) => setOutcomeForm({ ...outcomeForm, student_id: e.target.value })} />
            </Field>
            <Field label="Status">
              <select className="co-input" value={outcomeForm.status} onChange={(e) => setOutcomeForm({ ...outcomeForm, status: e.target.value })}>
                <option>DROPPED_OUT</option>
                <option>WITHDRAWN</option>
                <option>DISCONTINUED</option>
                <option>ACTIVE</option>
                <option>GRADUATED</option>
                <option>TRANSFERRED</option>
              </select>
            </Field>
            <Field label="Period">
              <input className="co-input" value={outcomeForm.period} onChange={(e) => setOutcomeForm({ ...outcomeForm, period: e.target.value })} placeholder="2025" />
            </Field>
          </div>
          <button type="button" className="co-btn mt-2" disabled={busy} onClick={recordOutcome}>Record outcome</button>
          <p className="mt-2 text-sm text-[#64748B]">{outcomes.length} stored outcomes (student IDs only).</p>
        </div>
      )}
    </div>
  );
}
