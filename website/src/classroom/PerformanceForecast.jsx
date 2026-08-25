import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { Notice } from "./ui";

function prettyFeature(name) {
  return String(name || "").replaceAll("_", " ").replace(" (1-10)", "");
}

function prettyBand(value) {
  return String(value || "").replaceAll("_", " ");
}

function detailsFor(model, mode) {
  if (mode === "calibration") return model?.calibration || model;
  return model;
}

function numericUsed(features) {
  if (!features) return [];
  return Object.entries(features).filter(([, value]) => typeof value === "number" && Number.isFinite(value));
}

export default function PerformanceForecast({ session, profile }) {
  const role = session?.user_role;
  const ownId = session?.student_data?.student_id;
  const studentId = role === "student" ? ownId : profile?.student_id;
  const canRun = role === "student" ? ownId != null : studentId != null;
  const [model, setModel] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [details, setDetails] = useState(false);
  const [mode, setMode] = useState("calibration");
  const [attendance, setAttendance] = useState("");
  const [midterm, setMidterm] = useState("");
  const [assignments, setAssignments] = useState("");
  const [quizzes, setQuizzes] = useState("");
  const [participation, setParticipation] = useState("");
  const [projects, setProjects] = useState("");
  const [studyHours, setStudyHours] = useState("");
  const [stress, setStress] = useState("");
  const [sleep, setSleep] = useState("");
  const gen = useRef(0);

  useEffect(() => {
    let alive = true;
    api.performanceModel()
      .then((row) => {
        if (alive) setModel(row);
      })
      .catch((err) => {
        if (alive) setError(err.message || "Prediction temporarily unavailable.");
      });
    return () => { alive = false; };
  }, []);

  const overrides = useMemo(() => {
    const out = {};
    if (attendance !== "") out["Attendance (%)"] = Number(attendance);
    if (midterm !== "") out.Midterm_Score = Number(midterm);
    if (assignments !== "") out.Assignments_Avg = Number(assignments);
    if (quizzes !== "") out.Quizzes_Avg = Number(quizzes);
    if (participation !== "") out.Participation_Score = Number(participation);
    if (projects !== "") out.Projects_Score = Number(projects);
    if (studyHours !== "") out.Study_Hours_per_Week = Number(studyHours);
    if (stress !== "") out["Stress_Level (1-10)"] = Number(stress);
    if (sleep !== "") out.Sleep_Hours_per_Night = Number(sleep);
    return out;
  }, [attendance, midterm, assignments, quizzes, participation, projects, studyHours, stress, sleep]);

  const run = async () => {
    if (!canRun) return;
    const token = ++gen.current;
    setBusy(true);
    setError("");
    try {
      const body = { features: overrides, mode };
      if (role !== "student") body.student_id = studentId;
      const row = await api.performancePredict(body);
      if (token !== gen.current) return;
      setResult(row);
    } catch (err) {
      if (token !== gen.current) return;
      setResult(null);
      setError(err.message || "Prediction temporarily unavailable.");
    } finally {
      if (token === gen.current) setBusy(false);
    }
  };

  useEffect(() => {
    if (!canRun) return undefined;
    const timer = setTimeout(() => { run(); }, 350);
    return () => clearTimeout(timer);
  }, [canRun, studentId, mode, JSON.stringify(overrides)]);

  const shown = detailsFor(model, mode);
  const studyScoreMode = mode === "calibration";
  const sent = numericUsed(result?.used_features);

  if (role !== "student" && studentId == null) {
    return (
      <article className="co-pred-card">
        <p className="co-section-kicker">Final-score forecast</p>
        <p className="text-sm text-[#64748B]">Select a student in this hub, then estimate their final score.</p>
      </article>
    );
  }

  return (
    <article className="co-pred-card space-y-3">
      <div>
        <p className="co-section-kicker">Final-score forecast</p>
        <h3>Predictive Intelligence</h3>
        <p className="co-pred-disclaimer">
          Near-real-time: the estimate refreshes as you edit (on-demand inference, not a live college grade feed).
          {studyScoreMode
            ? " Study Score sends the boxes below to the saved model. Stored CLASSORA attendance and marks are not mixed in."
            : " Public benchmark mode uses this student's stored CLASSORA fields when present. Final_Score barely depends on these boxes, so the number stays near the mean."}
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <button type="button" className={`co-btn ${mode === "calibration" ? "" : "co-btn-tertiary"}`} onClick={() => setMode("calibration")}>
          Study Score
        </button>
        <button type="button" className={`co-btn ${mode === "benchmark" ? "" : "co-btn-tertiary"}`} onClick={() => setMode("benchmark")}>
          Public benchmark
        </button>
      </div>
      {error && <Notice title="Prediction temporarily unavailable." body={error} tone="danger" />}
      <div className="grid gap-2 md:grid-cols-3">
        <label className="text-sm text-[#64748B]">
          Attendance (%)
          <input className="co-input mt-1" type="number" min="0" max="100" value={attendance} onChange={(e) => setAttendance(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Midterm score
          <input className="co-input mt-1" type="number" min="0" max="100" value={midterm} onChange={(e) => setMidterm(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Assignments avg
          <input className="co-input mt-1" type="number" min="0" max="100" value={assignments} onChange={(e) => setAssignments(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Quizzes avg
          <input className="co-input mt-1" type="number" min="0" max="100" value={quizzes} onChange={(e) => setQuizzes(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Participation (0–10)
          <input className="co-input mt-1" type="number" min="0" max="10" step="0.1" value={participation} onChange={(e) => setParticipation(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Projects score
          <input className="co-input mt-1" type="number" min="0" max="100" value={projects} onChange={(e) => setProjects(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Study hours / week
          <input className="co-input mt-1" type="number" min="0" max="40" value={studyHours} onChange={(e) => setStudyHours(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Stress (1–10)
          <input className="co-input mt-1" type="number" min="1" max="10" value={stress} onChange={(e) => setStress(e.target.value)} placeholder="Optional" />
        </label>
        <label className="text-sm text-[#64748B]">
          Sleep hours / night
          <input className="co-input mt-1" type="number" min="0" max="16" step="0.5" value={sleep} onChange={(e) => setSleep(e.target.value)} placeholder="Optional" />
        </label>
      </div>
      <p className="text-sm">
        Live estimate <strong>{result ? `${result.prediction} / 100` : "…"}</strong>
        {result ? ` · ${prettyBand(result.performance_band)}` : ""}
        {busy ? " · updating…" : ""}
      </p>
      {result && (
        <div className="space-y-2">
          {sent.length ? (
            <p className="co-pred-meta">
              Model input: {sent.map(([name, value]) => `${prettyFeature(name)} ${value}`).join(" · ")}
            </p>
          ) : (
            <p className="co-pred-meta">Empty boxes are imputed from training statistics, not this student's stored records.</p>
          )}
          <div>
            <p className="text-sm font-semibold">Important predictive factors</p>
            <ul className="list-disc pl-5 text-sm text-[#64748B]">
              {(result.important_factors || []).slice(0, 6).map((item) => (
                <li key={item.feature}>{prettyFeature(item.feature)}</li>
              ))}
            </ul>
            <p className="co-pred-disclaimer mt-1">Associated factors, not causes.</p>
          </div>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <button type="button" className="co-btn" disabled={busy} onClick={() => run()}>
          {busy ? "Updating…" : "Refresh now"}
        </button>
        <button type="button" className="co-btn co-btn-tertiary" onClick={() => setDetails((open) => !open)}>
          {details ? "Hide model details" : "Model details"}
        </button>
      </div>
      {details && shown && (
        <div className="text-sm text-[#64748B] space-y-1">
          <p>Mode: {studyScoreMode ? "Study Score" : "Public benchmark"}</p>
          <p>Dataset: {studyScoreMode ? "Study Score" : shown.dataset_name}</p>
          <p>Records: {shown.dataset_rows}</p>
          <p>Target: {shown.target}</p>
          <p>Features: {shown.feature_count}</p>
          <p>Model: {shown.model_type}</p>
          <p>Evaluation: MAE {shown.mae} · RMSE {shown.rmse} · R² {shown.r2}</p>
          <p>Training: {shown.trained_at} · {shown.model_version}</p>
          <p>Source: {studyScoreMode ? "Study Score model" : "Public/reference benchmark dataset"}</p>
          {!studyScoreMode && shown.dataset_label ? <p className="co-pred-disclaimer">{shown.dataset_label}</p> : null}
        </div>
      )}
    </article>
  );
}
