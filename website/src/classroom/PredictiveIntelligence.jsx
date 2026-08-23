import { useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { EmptyState, Field, Notice } from "./ui";

const TABS = [
  ["academic", "Academic"],
  ["career", "Career"],
  ["sources", "Data sources"],
  ["ask", "Ask"],
  ["planner", "Study planner"],
  ["history", "History"],
];

const MODES = [
  "GENERAL", "EXAM", "PASS_FOCUSED", "HIGH_SCORE",
  "HACKATHON", "INTERNSHIP", "PLACEMENT", "INTERVIEW", "CAREER",
];

function pretty(value) {
  return String(value || "—").replaceAll("_", " ");
}

function formatWhen(value) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}

function EvidenceList({ items }) {
  if (!items?.length) return <p className="text-sm text-[#64748B]">No linked source snippet is available.</p>;
  return (
    <ul className="co-pred-evidence">
      {items.map((item, index) => (
        <li key={`${item.documentId || "doc"}-${index}`}>
          <strong>{item.title || "Source"}</strong>
          {item.year ? <span> · {item.year}</span> : null}
          <span className="co-pred-kind">{pretty(item.kind || "OBSERVED")}</span>
          <p>{item.snippet}</p>
        </li>
      ))}
    </ul>
  );
}

function PredictionCard({ title, value, confidence, reason, action, disclaimer, evidence, status, period, onEvidence }) {
  return (
    <article className="co-pred-card" data-status={status || "PREDICTED"}>
      <p className="co-section-kicker">{title}</p>
      <h3>{value || pretty(status) || "Unavailable"}</h3>
      <p className="co-pred-meta">
        <span>Confidence: {pretty(confidence || "VERY LOW")}</span>
        {period ? <span> · Data period: {period}</span> : null}
        {status ? <span> · Status: {pretty(status)}</span> : null}
      </p>
      {reason ? <p className="text-sm">{reason}</p> : null}
      {action ? <p className="text-sm"><strong>Recommended: </strong>{action}</p> : null}
      {disclaimer ? <p className="co-pred-disclaimer">{disclaimer}</p> : null}
      {onEvidence || evidence?.length ? (
        <button type="button" className="co-btn co-btn-tertiary mt-2" onClick={onEvidence}>
          View evidence ({evidence?.length || 0})
        </button>
      ) : null}
    </article>
  );
}

function TopicRow({ item, onEvidence }) {
  return (
    <article className="co-pred-topic">
      <header>
        <h4>{item.topic}</h4>
        <span className="co-pred-priority" data-level={item.priority}>{pretty(item.priority)}</span>
      </header>
      <p className="co-pred-meta">
        Historical frequency: {item.historicalFrequency || "—"}
        {item.yearsAppeared?.length ? ` · Years: ${item.yearsAppeared.join(", ")}` : ""}
        {` · Confidence: ${pretty(item.confidence)}`}
      </p>
      <p className="text-sm">{item.why}</p>
      <p className="text-sm"><strong>Recommended: </strong>{item.recommendedAction}</p>
      <p className="co-pred-disclaimer">{item.disclaimer}</p>
      <button type="button" className="co-btn co-btn-tertiary mt-2" onClick={() => onEvidence(item.evidence || [])}>
        View evidence ({item.evidence?.length || 0})
      </button>
    </article>
  );
}

export function PredictionHealthSummary({ summary, onOpen }) {
  if (!summary?.available) {
    return <EmptyState title="No predictive data yet." body="Upload PYQs, notes, syllabus, or career records to generate evidence-based priorities." />;
  }
  return (
    <div className="space-y-3">
      <div className="co-chips">
        <div><em>Documents</em><strong>{summary.documentCount ?? "—"}</strong></div>
        <div><em>Ready</em><strong>{summary.readyCount ?? "—"}</strong></div>
        <div><em>Last question</em><strong>{summary.lastQuery || "None yet"}</strong></div>
      </div>
      {onOpen && <button type="button" className="co-btn" onClick={onOpen}>Open Predictive Intelligence</button>}
    </div>
  );
}

export default function PredictiveIntelligence({ session }) {
  const role = session?.user_role;
  const isStudent = role === "student";
  const isAdmin = role === "administrator";
  const isStaff = ["teacher", "faculty", "mentor", "counsellor", "administrator"].includes(role);
  const [tab, setTab] = useState("academic");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [overview, setOverview] = useState(null);
  const [documents, setDocuments] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [history, setHistory] = useState([]);
  const [plans, setPlans] = useState([]);
  const [evidence, setEvidence] = useState(null);
  const [subject, setSubject] = useState("DBMS");
  const [mode, setMode] = useState("GENERAL");
  const [days, setDays] = useState(7);
  const [hours, setHours] = useState(3);
  const [question, setQuestion] = useState("What should I prepare first for DBMS?");
  const [answer, setAnswer] = useState(null);
  const [paste, setPaste] = useState({ title: "", content: "", documentType: "", official: false });
  const [planDays, setPlanDays] = useState([]);
  const [settings, setSettings] = useState(null);

  const load = async () => {
    const [over, docs, hist, savedPlans] = await Promise.all([
      api.predictionOverview(),
      api.predictionDocuments(),
      api.predictionHistory(20),
      isStudent ? api.predictionPlans() : Promise.resolve({ plans: [] }),
    ]);
    setOverview(over);
    setDocuments(docs.documents || []);
    setHistory(hist.history || []);
    setPlans(savedPlans.plans || []);
    if (isAdmin) {
      try {
        const cfg = await api.predictionSettings();
        setSettings(cfg.settings || null);
      } catch {
        setSettings(null);
      }
    }
  };

  useEffect(() => {
    let alive = true;
    setLoading(true);
    load()
      .catch((err) => {
        if (alive) setError(err.message || "Predictive Intelligence could not be loaded.");
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => { alive = false; };
  }, []);

  const run = async (label, fn, okMessage) => {
    setBusy(label);
    setError("");
    setNotice("");
    try {
      const result = await fn();
      if (okMessage) setNotice(okMessage);
      await load();
      return result;
    } catch (err) {
      setError(err.message || "That request failed.");
      return null;
    } finally {
      setBusy("");
    }
  };

  const academic = analysis?.academic;
  const examDate = analysis?.examDate;
  const career = analysis?.career;
  const capabilities = overview?.capabilities || {};

  const statusHint = useMemo(() => {
    if (busy === "upload") return "Extracting and classifying the uploaded source…";
    if (busy === "analyze") return "Analyzing historical patterns and current material…";
    if (busy === "query") return "Retrieving evidence and generating a structured prediction…";
    return "";
  }, [busy]);

  return (
    <div className="space-y-4">
      <div>
        <p className="co-section-kicker">Predictive Intelligence</p>
        <h2 className="text-xl font-semibold">Plan from evidence, not guarantees</h2>
        <p className="text-sm text-[#64748B]">
          Predictions are pattern-based. Official notices override estimates. Current syllabus overrides outdated history.
          Uploaded files are treated as data, never as system instructions.
        </p>
      </div>
      {error && <Notice title="Predictive Intelligence" body={error} tone="danger" />}
      {notice && <Notice title="Updated" body={notice} tone="ok" />}
      {statusHint && <Notice title="Working" body={statusHint} tone="info" />}
      <div className="co-modules" role="tablist" aria-label="Predictive Intelligence sections">
        {TABS.map(([id, label]) => (
          <button key={id} type="button" className={`co-btn ${tab === id ? "" : "co-btn-secondary"}`} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {loading ? <p className="text-sm text-[#64748B]">Loading Predictive Intelligence…</p> : null}

      {tab === "academic" && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-4">
            <Field label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
            <Field label="Mode" as="select" value={mode} onChange={(e) => setMode(e.target.value)}>
              {MODES.map((item) => <option key={item} value={item}>{pretty(item)}</option>)}
            </Field>
            <Field label="Days" type="number" min="1" max="60" value={days} onChange={(e) => setDays(Number(e.target.value) || 7)} />
            <button
              type="button"
              className="co-btn self-end"
              disabled={!!busy}
              onClick={() => run("analyze", async () => {
                const result = await api.analyzePredictions({ subject, mode, days, hours });
                setAnalysis(result);
                setPlanDays(result.plan?.days || []);
                return result;
              }, "Academic analysis finished.")}
            >
              {busy === "analyze" ? "Analyzing…" : "Generate academic predictions"}
            </button>
          </div>
          {!academic && <EmptyState title="No academic prediction yet." body="Upload at least two years of PYQs plus current syllabus/notes, then generate predictions." />}
          {academic?.status === "INSUFFICIENT" && (
            <Notice title="Insufficient historical data" body={academic.insufficientReason} tone="warn" />
          )}
          {examDate && (
            <PredictionCard
              title="Exam date prediction"
              value={
                examDate.status === "OFFICIAL"
                  ? `Official: ${examDate.official?.windowStart || examDate.official?.dates?.[0] || "see notice"}`
                  : examDate.predicted
                    ? `${examDate.predicted.windowStart} to ${examDate.predicted.windowEnd}`
                    : pretty(examDate.status)
              }
              confidence={examDate.confidence}
              status={examDate.status}
              reason={examDate.why}
              disclaimer={examDate.disclaimer}
              evidence={examDate.evidence}
              period={(examDate.yearsAnalyzed || []).join(", ")}
              onEvidence={() => setEvidence(examDate.evidence || [])}
            />
          )}
          <div className="co-pred-grid">
            {(academic?.studyPriorities || []).map((item) => (
              <TopicRow key={item.topicKey || item.topic} item={item} onEvidence={setEvidence} />
            ))}
          </div>
          {analysis?.today?.items?.length ? (
            <div className="co-card">
              <h3 className="mb-2 font-semibold">What should I study today?</h3>
              <p className="text-sm text-[#64748B]">{analysis.today.why}</p>
              <ol className="mt-2 list-decimal pl-5">
                {analysis.today.items.map((item) => <li key={item.topic}>{item.topic} · {pretty(item.priority)}</li>)}
              </ol>
            </div>
          ) : null}
        </div>
      )}

      {tab === "career" && (
        <div className="space-y-4">
          <button
            type="button"
            className="co-btn"
            disabled={!!busy}
            onClick={() => run("analyze", async () => {
              const result = await api.analyzePredictions({ domain: "CAREER", mode });
              setAnalysis(result);
              return result;
            }, "Career analysis finished.")}
          >
            {busy === "analyze" ? "Analyzing…" : "Analyze career sources"}
          </button>
          {career?.status === "INSUFFICIENT" && <Notice title="Insufficient career data" body={career.insufficientReason} tone="warn" />}
          <div className="co-pred-grid">
            {(career?.skills || []).map((item) => (
              <article key={item.label} className="co-pred-card">
                <p className="co-section-kicker">Observed skill</p>
                <h3>{item.label}</h3>
                <p className="co-pred-meta">{item.count} uploaded records · {pretty(item.confidence)}</p>
                <p className="co-pred-disclaimer">{item.disclaimer}</p>
              </article>
            ))}
          </div>
          {career?.stipend && (
            <PredictionCard
              title="Internship stipend range"
              value={
                career.stipend.status === "ESTIMATED"
                  ? `₹${career.stipend.typicalRange?.min}–₹${career.stipend.typicalRange?.max} typical`
                  : pretty(career.stipend.status)
              }
              status={career.stipend.status}
              confidence={career.stipend.confidence}
              reason={career.stipend.insufficientReason || `Observed from ${career.stipend.n || 0} numeric records only.`}
              disclaimer={career.stipend.disclaimer}
              evidence={career.stipend.evidence}
              onEvidence={() => setEvidence(career.stipend.evidence || [])}
            />
          )}
          {analysis?.hackathonPrep && (
            <div className="co-card">
              <h3 className="mb-2 font-semibold">Hackathon preparation</h3>
              <p className="co-pred-disclaimer">{analysis.hackathonPrep.disclaimer}</p>
              <p className="text-sm">{analysis.hackathonPrep.note}</p>
              <p className="mt-2 text-sm"><strong>Potential questions</strong></p>
              <ul className="list-disc pl-5 text-sm">
                {(analysis.hackathonPrep.checklists?.qa || []).map((item) => <li key={item}>{item}</li>)}
              </ul>
            </div>
          )}
          {analysis?.jobMatch && (
            <div className="co-card">
              <h3 className="mb-2 font-semibold">Job match</h3>
              <p>Matching: {(analysis.jobMatch.matching || []).join(", ") || "—"}</p>
              <p>Missing: {(analysis.jobMatch.missing || []).join(", ") || "—"}</p>
              <p className="text-sm">{analysis.jobMatch.recommendedAction}</p>
              <p className="co-pred-disclaimer">{analysis.jobMatch.disclaimer}</p>
            </div>
          )}
        </div>
      )}

      {tab === "sources" && (
        <div className="space-y-4">
          <div className="co-card space-y-3">
            <h3 className="font-semibold">Add data</h3>
            <p className="text-sm text-[#64748B]">
              TXT, CSV, MD, JSON{capabilities.pdf ? ", PDF" : ""}{capabilities.docx ? ", DOCX" : ""} accepted.
              Images are not OCR’d. URLs are stored only if you also paste the text. Maximum 2 MB.
            </p>
            <Field label="Title" value={paste.title} onChange={(e) => setPaste({ ...paste, title: e.target.value })} />
            <Field label="Optional type correction" as="select" value={paste.documentType} onChange={(e) => setPaste({ ...paste, documentType: e.target.value })}>
              <option value="">Detect from content</option>
              {(overview?.types || []).map((item) => <option key={item} value={item}>{pretty(item)}</option>)}
            </Field>
            <Field label="Paste source text" as="textarea" rows={6} value={paste.content} onChange={(e) => setPaste({ ...paste, content: e.target.value })} />
            {isStaff && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={paste.official} onChange={(e) => setPaste({ ...paste, official: e.target.checked })} />
                Mark as official institutional notice
              </label>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className="co-btn"
                disabled={!!busy || !paste.content.trim()}
                onClick={() => run("upload", () => api.addPredictionText({
                  title: paste.title || "Pasted source",
                  content: paste.content,
                  documentType: paste.documentType,
                  official: paste.official,
                }), "Source stored and classified.")}
              >
                {busy === "upload" ? "Analyzing…" : "Add pasted source"}
              </button>
              <label className="co-btn co-btn-secondary">
                Browse files
                <input
                  type="file"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    run("upload", () => api.uploadPredictionFile(file, {
                      title: paste.title || file.name,
                      documentType: paste.documentType,
                      official: paste.official,
                    }), "File processed.");
                    event.target.value = "";
                  }}
                />
              </label>
            </div>
          </div>
          <div className="co-table-wrap">
            <table className="co-table">
              <thead>
                <tr><th>Document</th><th>Type</th><th>Subject</th><th>Year</th><th>Status</th><th></th></tr>
              </thead>
              <tbody>
                {documents.map((doc) => (
                  <tr key={doc.id}>
                    <td>{doc.title}<div className="text-xs text-[#64748B]">{formatWhen(doc.uploadedAt)}</div></td>
                    <td>{pretty(doc.documentType)}</td>
                    <td>{doc.subject || "UNKNOWN"}</td>
                    <td>{doc.year || "UNKNOWN"}</td>
                    <td><span className="co-pred-status" data-status={doc.status}>{pretty(doc.status)}</span>{doc.error ? <div className="text-xs">{doc.error}</div> : null}</td>
                    <td className="space-x-2">
                      {doc.status === "FAILED" && <button type="button" className="co-btn co-btn-tertiary" onClick={() => run("upload", () => api.reprocessPredictionDocument(doc.id), "Reprocessed.")}>Retry</button>}
                      <button type="button" className="co-btn co-btn-tertiary" onClick={() => run("upload", () => api.deletePredictionDocument(doc.id), "Removed.")}>Delete</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {!documents.length && <EmptyState title="No sources yet." body="Paste PYQs, notes, syllabus, schedules, or career records." />}
          </div>
        </div>
      )}

      {tab === "ask" && (
        <div className="space-y-4">
          <Field label="Ask from analyzed evidence" as="textarea" rows={3} value={question} onChange={(e) => setQuestion(e.target.value)} />
          <button
            type="button"
            className="co-btn"
            disabled={!!busy || !question.trim()}
            onClick={() => run("query", async () => {
              const result = await api.predictionQuery({ question, subject, mode, days, hours });
              setAnswer(result);
              setAnalysis(result);
              setPlanDays(result.academic ? (await Promise.resolve(result)).today : result.today);
              return result;
            }, "Answer generated from stored sources.")}
          >
            {busy === "query" ? "Retrieving evidence…" : "Ask"}
          </button>
          {answer?.card && (
            <div className="co-card space-y-2">
              <p className="co-section-kicker">{pretty(answer.intent)}</p>
              <h3>{answer.card.title || "Prediction"}</h3>
              {answer.card.insufficientReason && <Notice title="Insufficient data" body={answer.card.insufficientReason} tone="warn" />}
              {(answer.card.items || []).slice(0, 8).map((item) => (
                <p key={item.topic || item.label || item.path}>
                  <strong>{item.topic || item.label || item.path}</strong>
                  {item.priority ? ` · ${pretty(item.priority)}` : ""}
                  {item.historicalFrequency ? ` · ${item.historicalFrequency}` : ""}
                  {item.count ? ` · ${item.count} records` : ""}
                </p>
              ))}
              {answer.card.predicted && (
                <p>Estimated window: {answer.card.predicted.windowStart} to {answer.card.predicted.windowEnd}. This is not an official schedule.</p>
              )}
              <p className="co-pred-disclaimer">{answer.card.disclaimer || answer.disclaimer}</p>
            </div>
          )}
        </div>
      )}

      {tab === "planner" && (
        <div className="space-y-4">
          <div className="grid gap-3 md:grid-cols-3">
            <Field label="Days" type="number" min="1" max="60" value={days} onChange={(e) => setDays(Number(e.target.value) || 7)} />
            <Field label="Hours / day" type="number" min="1" max="12" value={hours} onChange={(e) => setHours(Number(e.target.value) || 3)} />
            <button
              type="button"
              className="co-btn self-end"
              disabled={!!busy}
              onClick={() => run("analyze", async () => {
                const result = await api.analyzePredictions({ subject, mode, days, hours });
                setAnalysis(result);
                setPlanDays(result.plan?.days || []);
                return result;
              }, "Plan drafted. You can edit it.")}
            >
              Draft plan
            </button>
          </div>
          {!planDays.length && <EmptyState title="No plan yet." body="Generate academic predictions first, then draft a plan you can edit." />}
          {planDays.map((day, index) => (
            <div key={day.day} className="co-card grid gap-2 md:grid-cols-3">
              <Field label={`Day ${day.day} subject`} value={day.subject || ""} onChange={(e) => {
                const next = [...planDays];
                next[index] = { ...day, subject: e.target.value, kind: "RECOMMENDED" };
                setPlanDays(next);
              }} />
              <Field label="Topic" value={day.topic || ""} onChange={(e) => {
                const next = [...planDays];
                next[index] = { ...day, topic: e.target.value };
                setPlanDays(next);
              }} />
              <Field label="Hours" type="number" value={day.hours || hours} onChange={(e) => {
                const next = [...planDays];
                next[index] = { ...day, hours: Number(e.target.value) || hours };
                setPlanDays(next);
              }} />
            </div>
          ))}
          {isStudent && planDays.length > 0 && (
            <button type="button" className="co-btn" disabled={!!busy} onClick={() => run("analyze", () => api.savePredictionPlan({
              subject, mode, days: planDays, userModified: true,
            }), "Plan saved. You can keep changing it.")}>
              Save my edited plan
            </button>
          )}
          {plans.length > 0 && <p className="text-sm text-[#64748B]">{plans.length} saved plan(s) on this account.</p>}
        </div>
      )}

      {tab === "history" && (
        <div className="space-y-3">
          {!history.length && <EmptyState title="No previous predictions." body="Ask a question or generate an analysis to keep a reviewable history." />}
          {history.map((row) => (
            <article key={row.id} className="co-card">
              <p className="co-section-kicker">{pretty(row.predictionType)} · {formatWhen(row.generatedAt)}</p>
              <h3 className="font-semibold">{row.question || "Analysis"}</h3>
              <p className="co-pred-meta">{pretty(row.status)} · {pretty(row.confidence)} · {row.dataPeriod || "—"}</p>
              {isStaff || isStudent ? (
                <button
                  type="button"
                  className="co-btn co-btn-tertiary mt-2"
                  onClick={() => {
                    const actual = window.prompt("Actual outcome (optional, for later evaluation)");
                    if (!actual) return;
                    run("analyze", () => api.recordPredictionOutcome(row.id, { actualOutcome: actual }), "Outcome stored for evaluation. Production models are not auto-retrained.");
                  }}
                >
                  Record actual outcome
                </button>
              ) : null}
            </article>
          ))}
        </div>
      )}

      {isAdmin && settings && tab === "sources" && (
        <div className="co-card space-y-2">
          <h3 className="font-semibold">Scoring weights</h3>
          <p className="text-sm text-[#64748B]">Transparent and configurable. These are not unexplained AI scores.</p>
          {Object.entries(settings.weights || {}).map(([key, value]) => (
            <p key={key} className="text-sm">{pretty(key)}: {Number(value).toFixed(2)}</p>
          ))}
        </div>
      )}

      {evidence && (
        <div className="co-card">
          <h3 className="mb-2 font-semibold">Evidence</h3>
          <EvidenceList items={evidence} />
          <button type="button" className="co-btn co-btn-secondary mt-3" onClick={() => setEvidence(null)}>Close evidence</button>
        </div>
      )}
    </div>
  );
}
